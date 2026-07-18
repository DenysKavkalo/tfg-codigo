#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 2) {
  stop(
    paste(
      "Uso:",
      "Rscript R/temporal_analysis.R",
      "<clean_reviews_csv> <output_dir> [start_date] [end_date]"
    ),
    call. = FALSE
  )
}

input_csv <- args[[1]]
output_dir <- args[[2]]
start_date <- as.Date(if (length(args) >= 3) args[[3]] else "2024-01-01")
end_date <- as.Date(if (length(args) >= 4) args[[4]] else "2025-12-31")

script_argument <- grep("^--file=", commandArgs(), value = TRUE)
script_path <- if (length(script_argument) > 0) {
  normalizePath(sub("^--file=", "", script_argument[[1]]))
} else {
  normalizePath("R/temporal_analysis.R")
}
source(file.path(dirname(script_path), "plot_utils.R"))

if (is.na(start_date) || is.na(end_date) || start_date > end_date) {
  stop("El periodo temporal indicado no es valido.", call. = FALSE)
}

run_temporal_analysis <- function(input_csv, output_dir, start_date, end_date) {
reviews <- read.csv(input_csv, stringsAsFactors = FALSE)
required_columns <- c("hotel_id", "platform", "review_date", "rating_scaled_0_10")
missing_columns <- setdiff(required_columns, names(reviews))
if (length(missing_columns) > 0) {
  stop(
    paste("Faltan columnas obligatorias:", paste(missing_columns, collapse = ", ")),
    call. = FALSE
  )
}

reviews$review_date <- as.Date(reviews$review_date)
reviews <- reviews[
  !is.na(reviews$review_date) &
    !is.na(reviews$rating_scaled_0_10) &
    reviews$review_date >= start_date &
    reviews$review_date <= end_date,
]
if (nrow(reviews) == 0) {
  stop("No hay valoraciones dentro del periodo indicado.", call. = FALSE)
}

reviews$year <- as.integer(format(reviews$review_date, "%Y"))
reviews$month <- as.Date(format(reviews$review_date, "%Y-%m-01"))

annual_summary <- grouped_summary(reviews, c("hotel_id", "platform", "year"))
monthly_observed <- grouped_summary(reviews, c("hotel_id", "platform", "month"))
monthly_summary <- complete_month_grid(
  monthly_observed,
  reviews,
  start_date,
  end_date
)
granularity <- score_granularity(reviews)

if (!dir.exists(output_dir)) {
  dir.create(output_dir, recursive = TRUE)
}

write.csv(
  annual_summary,
  file.path(output_dir, "annual_summary.csv"),
  row.names = FALSE
)
write.csv(
  monthly_summary,
  file.path(output_dir, "monthly_summary.csv"),
  row.names = FALSE
)
write.csv(
  granularity,
  file.path(output_dir, "score_granularity.csv"),
  row.names = FALSE
)
write_monthly_counts_plot(
  monthly_summary,
  file.path(output_dir, "monthly_review_counts.png")
)
write_monthly_means_plot(
  monthly_summary,
  file.path(output_dir, "monthly_mean_scores.png")
)

message(
  "Analisis temporal escrito en ", output_dir,
  " para el periodo ", start_date, " a ", end_date, "."
)
}


grouped_summary <- function(data, grouping_columns) {
  groups <- split(data, interaction(data[grouping_columns], drop = TRUE))
  output <- do.call(
    rbind,
    lapply(groups, function(group) {
      scores <- group$rating_scaled_0_10
      keys <- group[1, grouping_columns, drop = FALSE]
      cbind(
        keys,
        data.frame(
          n_reviews = length(scores),
          mean_score = mean(scores),
          sd_score = if (length(scores) > 1) sd(scores) else NA_real_,
          median_score = median(scores),
          min_score = min(scores),
          max_score = max(scores),
          stringsAsFactors = FALSE
        )
      )
    })
  )
  rownames(output) <- NULL
  output
}


complete_month_grid <- function(monthly_observed, reviews, start_date, end_date) {
  months <- seq(
    as.Date(format(start_date, "%Y-%m-01")),
    as.Date(format(end_date, "%Y-%m-01")),
    by = "month"
  )
  grid <- expand.grid(
    hotel_id = sort(unique(reviews$hotel_id)),
    platform = sort(unique(reviews$platform)),
    month = months,
    stringsAsFactors = FALSE
  )
  grid$month <- as.Date(grid$month, origin = "1970-01-01")
  monthly_observed$month <- as.Date(monthly_observed$month)
  output <- merge(
    grid,
    monthly_observed,
    by = c("hotel_id", "platform", "month"),
    all.x = TRUE,
    sort = TRUE
  )
  output$n_reviews[is.na(output$n_reviews)] <- 0L
  output$year <- as.integer(format(output$month, "%Y"))
  output$month_number <- as.integer(format(output$month, "%m"))
  output$has_reviews <- output$n_reviews > 0
  output
}


score_granularity <- function(reviews) {
  groups <- split(
    reviews,
    list(reviews$hotel_id, reviews$platform),
    drop = TRUE
  )
  output <- do.call(
    rbind,
    lapply(groups, function(group) {
      scores <- group$rating_scaled_0_10
      unique_scores <- sort(unique(scores))
      increments <- diff(unique_scores)
      positive_increments <- increments[increments > 1e-9]
      data.frame(
        hotel_id = group$hotel_id[[1]],
        platform = group$platform[[1]],
        n_reviews = length(scores),
        n_unique_scores = length(unique_scores),
        minimum_observed_increment = if (length(positive_increments) > 0) {
          min(positive_increments)
        } else {
          NA_real_
        },
        n_fractional_scores = sum(abs(scores - round(scores)) > 1e-9),
        proportion_fractional_scores = mean(abs(scores - round(scores)) > 1e-9),
        stringsAsFactors = FALSE
      )
    })
  )
  output[order(output$hotel_id, output$platform), ]
}


write_monthly_counts_plot <- function(monthly_summary, output_path) {
  platforms <- sort(unique(monthly_summary$platform))
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
    mar = c(4.5, 4.8, 3, 0.8),
    mgp = c(2.7, 0.8, 0),
    tcl = -0.25,
    las = 1
  )
  on.exit({
    par(old_par)
    dev.off()
  }, add = TRUE)

  for (platform in platforms) {
    current <- monthly_summary[monthly_summary$platform == platform, ]
    plot(
      current$month,
      current$n_reviews,
      type = "o",
      pch = 19,
      col = "#2171b5",
      main = platform_display_name(platform),
      xlab = "Mes",
      ylab = "N\u00famero de rese\u00f1as",
      ylim = c(0, max(current$n_reviews) * 1.1 + 1)
    )
  }
}


write_monthly_means_plot <- function(monthly_summary, output_path) {
  platforms <- sort(unique(monthly_summary$platform))
  colours <- c("#1b9e77", "#d95f02", "#7570b3", "#e7298a")
  line_types <- c(1, 2, 3, 4)
  point_types <- c(16, 17, 15, 18)
  png(
    filename = output_path,
    width = 1400,
    height = 750,
    res = 130,
    pointsize = 16,
    bg = "white"
  )
  old_par <- par(
    mar = c(4.5, 5, 1.2, 0.8),
    mgp = c(2.8, 0.8, 0),
    tcl = -0.25,
    las = 1
  )
  on.exit({
    par(old_par)
    dev.off()
  }, add = TRUE)
  plot(
    range(monthly_summary$month),
    c(0, 10),
    type = "n",
    xlab = "Mes",
    ylab = "Puntuaci\u00f3n media en escala 0-10"
  )
  grid(col = "#dddddd")
  for (index in seq_along(platforms)) {
    current <- monthly_summary[monthly_summary$platform == platforms[[index]], ]
    lines(
      current$month,
      current$mean_score,
      type = "o",
      pch = point_types[[index]],
      lty = line_types[[index]],
      lwd = 2,
      col = colours[[index]]
    )
  }
  legend(
    "bottomleft",
    legend = platform_display_name(platforms),
    col = colours[seq_along(platforms)],
    lty = line_types[seq_along(platforms)],
    pch = point_types[seq_along(platforms)],
    bty = "n",
    ncol = 2,
    cex = 0.9,
    x.intersp = 0.7,
    y.intersp = 0.8
  )
}


run_temporal_analysis(input_csv, output_dir, start_date, end_date)
