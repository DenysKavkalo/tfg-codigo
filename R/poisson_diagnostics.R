#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 2) {
  stop(
    paste(
      "Uso:",
      "Rscript R/poisson_diagnostics.R",
      "<clean_reviews_csv> <output_dir> [replicates] [seed]"
    ),
    call. = FALSE
  )
}

input_csv <- args[[1]]
output_dir <- args[[2]]
replicates <- if (length(args) >= 3) as.integer(args[[3]]) else 5000L
seed <- if (length(args) >= 4) as.integer(args[[4]]) else 20240601L

if (is.na(replicates) || replicates < 100) {
  stop("replicates debe ser un entero igual o superior a 100.", call. = FALSE)
}
if (is.na(seed)) {
  stop("seed debe ser un entero.", call. = FALSE)
}

script_argument <- grep("^--file=", commandArgs(), value = TRUE)
script_path <- if (length(script_argument) > 0) {
  normalizePath(sub("^--file=", "", script_argument[[1]]))
} else {
  normalizePath("R/poisson_diagnostics.R")
}
source(file.path(dirname(script_path), "partition_model.R"))
source(file.path(dirname(script_path), "plot_utils.R"))

run_diagnostics <- function(input_csv, output_dir, replicates, seed) {
reviews <- read.csv(input_csv, stringsAsFactors = FALSE)
required_columns <- c("hotel_id", "platform", "rating_scaled_0_10")
missing_columns <- setdiff(required_columns, names(reviews))
if (length(missing_columns) > 0) {
  stop(
    paste("Faltan columnas obligatorias:", paste(missing_columns, collapse = ", ")),
    call. = FALSE
  )
}

reviews <- reviews[!is.na(reviews$rating_scaled_0_10), ]
if (nrow(reviews) == 0) {
  stop("No hay puntuaciones validas para diagnosticar.", call. = FALSE)
}
if (any(reviews$rating_scaled_0_10 < 0 | reviews$rating_scaled_0_10 > 10)) {
  stop("Las puntuaciones deben encontrarse en la escala 0-10.", call. = FALSE)
}

reviews$transformed_score <- transform_partition_scores(
  reviews$rating_scaled_0_10,
  "round"
)
groups <- split(
  reviews,
  list(reviews$hotel_id, reviews$platform),
  drop = TRUE
)

set.seed(seed)
diagnostics <- do.call(
  rbind,
  lapply(groups, function(group) diagnose_poisson_group(group, replicates))
)
diagnostics <- diagnostics[order(diagnostics$hotel_id, diagnostics$platform), ]

frequencies <- do.call(
  rbind,
  lapply(groups, poisson_frequency_rows)
)
frequencies <- frequencies[
  order(frequencies$hotel_id, frequencies$platform, frequencies$transformed_score),
]

if (!dir.exists(output_dir)) {
  dir.create(output_dir, recursive = TRUE)
}

write.csv(
  diagnostics,
  file.path(output_dir, "poisson_diagnostics.csv"),
  row.names = FALSE
)
write.csv(
  frequencies,
  file.path(output_dir, "poisson_frequency_comparison.csv"),
  row.names = FALSE
)
write_poisson_plot(
  frequencies,
  file.path(output_dir, "poisson_fit_by_platform.png")
)

message(
  "Diagnostico de Poisson escrito en ", output_dir,
  " (", replicates, " replicas; semilla ", seed, ")."
)
}


diagnose_poisson_group <- function(group, replicates) {
  scores <- group$transformed_score
  n <- length(scores)
  observed_mean <- mean(scores)
  observed_variance <- var(scores)
  observed_dispersion <- safe_ratio(observed_variance, observed_mean)
  observed_zero_rate <- mean(scores == 0)
  observed_maximum <- max(scores)

  replicated_statistics <- replicate(
    replicates,
    {
      lambda <- rgamma(1, shape = sum(scores) + 0.5, rate = n)
      replicated <- rpois(n, lambda)
      replicated_mean <- mean(replicated)
      c(
        dispersion = safe_ratio(var(replicated), replicated_mean),
        zero_rate = mean(replicated == 0),
        maximum = max(replicated)
      )
    }
  )

  dispersion_p <- upper_tail_probability(
    replicated_statistics["dispersion", ],
    observed_dispersion
  )
  zero_p <- two_sided_tail_probability(
    replicated_statistics["zero_rate", ],
    observed_zero_rate
  )
  maximum_p <- two_sided_tail_probability(
    replicated_statistics["maximum", ],
    observed_maximum
  )

  interpretation <- if (!is.na(dispersion_p) && dispersion_p < 0.05) {
    "overdispersion_not_reproduced_by_poisson"
  } else {
    "no_overdispersion_signal_at_0.05"
  }

  data.frame(
    hotel_id = group$hotel_id[[1]],
    platform = group$platform[[1]],
    n_reviews = n,
    mean_transformed = observed_mean,
    variance_transformed = observed_variance,
    dispersion_index = observed_dispersion,
    observed_zero_rate = observed_zero_rate,
    fitted_zero_rate = exp(-observed_mean),
    observed_maximum = observed_maximum,
    pp_dispersion_upper_p = dispersion_p,
    pp_zero_two_sided_p = zero_p,
    pp_maximum_two_sided_p = maximum_p,
    replicates = replicates,
    interpretation = interpretation,
    stringsAsFactors = FALSE
  )
}


poisson_frequency_rows <- function(group) {
  scores <- group$transformed_score
  support <- 0:10
  observed_counts <- tabulate(scores + 1L, nbins = length(support))
  lambda <- mean(scores)
  data.frame(
    hotel_id = group$hotel_id[[1]],
    platform = group$platform[[1]],
    transformed_score = support,
    observed_relative_frequency = observed_counts / length(scores),
    fitted_poisson_probability = dpois(support, lambda),
    fitted_probability_above_10 = ppois(10, lambda, lower.tail = FALSE),
    stringsAsFactors = FALSE
  )
}


write_poisson_plot <- function(frequencies, output_path) {
  platforms <- sort(unique(frequencies$platform))
  png(
    filename = output_path,
    width = 1400,
    height = 950,
    res = 130,
    pointsize = 16,
    bg = "white"
  )
  old_par <- par(
    mfrow = c(ceiling(length(platforms) / 2), 2),
    mar = c(4.6, 4.8, 3, 0.8),
    mgp = c(2.7, 0.8, 0),
    tcl = -0.25,
    las = 1
  )
  on.exit({
    par(old_par)
    dev.off()
  }, add = TRUE)

  for (platform in platforms) {
    current <- frequencies[frequencies$platform == platform, ]
    upper <- max(
      current$observed_relative_frequency,
      current$fitted_poisson_probability
    ) * 1.12
    centers <- barplot(
      current$observed_relative_frequency,
      names.arg = current$transformed_score,
      ylim = c(0, upper),
      main = platform_display_name(platform),
      xlab = "Puntuaci\u00f3n transformada (10-S)",
      ylab = "Frecuencia relativa",
      col = "#9ecae1",
      border = "white"
    )
    lines(
      centers,
      current$fitted_poisson_probability,
      type = "b",
      pch = 19,
      col = "#cb181d",
      lwd = 2
    )
    legend(
      "topright",
      legend = c("Observada", "Poisson ajustada"),
      fill = c("#9ecae1", NA),
      border = c("white", NA),
      lty = c(NA, 1),
      pch = c(NA, 19),
      col = c("#9ecae1", "#cb181d"),
      bty = "n",
      cex = 0.8,
      x.intersp = 0.7,
      y.intersp = 0.8
    )
  }
}


safe_ratio <- function(numerator, denominator) {
  if (is.na(denominator) || denominator <= 0) {
    return(NA_real_)
  }
  numerator / denominator
}


upper_tail_probability <- function(simulated, observed) {
  simulated <- simulated[is.finite(simulated)]
  if (!is.finite(observed) || length(simulated) == 0) {
    return(NA_real_)
  }
  (sum(simulated >= observed) + 1) / (length(simulated) + 1)
}


two_sided_tail_probability <- function(simulated, observed) {
  simulated <- simulated[is.finite(simulated)]
  if (!is.finite(observed) || length(simulated) == 0) {
    return(NA_real_)
  }
  lower <- (sum(simulated <= observed) + 1) / (length(simulated) + 1)
  upper <- (sum(simulated >= observed) + 1) / (length(simulated) + 1)
  min(1, 2 * min(lower, upper))
}


run_diagnostics(input_csv, output_dir, replicates, seed)
