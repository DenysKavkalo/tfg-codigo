#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 2) {
  stop(
    paste(
      "Uso:",
      "Rscript R/review_distributions.R",
      "<clean_reviews_csv> <output_dir>"
    ),
    call. = FALSE
  )
}

input_csv <- args[[1]]
output_dir <- args[[2]]

script_argument <- grep("^--file=", commandArgs(), value = TRUE)
script_path <- if (length(script_argument) > 0) {
  normalizePath(sub("^--file=", "", script_argument[[1]]))
} else {
  normalizePath("R/review_distributions.R")
}
source(file.path(dirname(script_path), "plot_utils.R"))

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
  stop("No hay valoraciones validas para analizar.", call. = FALSE)
}

if (!dir.exists(output_dir)) {
  dir.create(output_dir, recursive = TRUE)
}

summary_rows <- do.call(
  rbind,
  lapply(
    split(reviews, list(reviews$hotel_id, reviews$platform), drop = TRUE),
    function(group) {
      scores <- group$rating_scaled_0_10
      data.frame(
        hotel_id = group$hotel_id[[1]],
        platform = group$platform[[1]],
        n_reviews = length(scores),
        mean_score = mean(scores),
        sd_score = sd(scores),
        min_score = min(scores),
        q25_score = as.numeric(quantile(scores, 0.25)),
        median_score = median(scores),
        q75_score = as.numeric(quantile(scores, 0.75)),
        max_score = max(scores),
        stringsAsFactors = FALSE
      )
    }
  )
)

write.csv(
  summary_rows,
  file.path(output_dir, "distribution_summary.csv"),
  row.names = FALSE
)

png(
  filename = file.path(output_dir, "histograms_by_platform.png"),
  width = 1400,
  height = 900,
  res = 130,
  pointsize = 16,
  bg = "white"
)
platforms <- sort(unique(reviews$platform))
histogram_breaks <- seq(0, 10, by = 1)
histogram_specs <- lapply(
  platforms,
  function(platform) {
    hist(
      reviews$rating_scaled_0_10[reviews$platform == platform],
      breaks = histogram_breaks,
      plot = FALSE
    )
  }
)
common_density_limit <- max(
  unlist(lapply(histogram_specs, function(specification) specification$density))
) * 1.08
par(
  mfrow = c(ceiling(length(platforms) / 2), 2),
  mar = c(4.5, 4.8, 3, 0.8),
  mgp = c(2.7, 0.8, 0),
  tcl = -0.25,
  las = 1
)
for (platform in platforms) {
  scores <- reviews$rating_scaled_0_10[reviews$platform == platform]
  hist(
    scores,
    breaks = histogram_breaks,
    freq = FALSE,
    main = platform_display_name(platform),
    xlab = "Puntuaci\u00f3n en escala 0-10",
    ylab = "Frecuencia relativa",
    col = "#9ecae1",
    border = "white",
    xlim = c(0, 10),
    ylim = c(0, common_density_limit)
  )
}
dev.off()

png(
  filename = file.path(output_dir, "boxplot_by_platform.png"),
  width = 1400,
  height = 760,
  res = 130,
  pointsize = 16,
  bg = "white"
)
boxplot_platforms <- rev(platforms)
boxplot_scores <- lapply(
  boxplot_platforms,
  function(platform) {
    reviews$rating_scaled_0_10[reviews$platform == platform]
  }
)
par(
  mar = c(4.5, 11, 1, 1),
  mgp = c(2.6, 0.7, 0),
  tcl = -0.25,
  xaxs = "i"
)
boxplot(
  boxplot_scores,
  names = platform_display_name(boxplot_platforms),
  horizontal = TRUE,
  ylim = c(0, 10.25),
  xlab = "Puntuaci\u00f3n en escala 0-10",
  ylab = "",
  col = "#c7e9c0",
  border = "#238b45",
  medcol = "#006d2c",
  medlwd = 2,
  whisklty = 1,
  staplewex = 0.6,
  outpch = 21,
  outbg = "white",
  outcol = "#238b45",
  outcex = 0.75,
  las = 1,
  cex.axis = 1.05,
  cex.lab = 1.1
)
dev.off()

message("Analisis descriptivo escrito en ", output_dir)
