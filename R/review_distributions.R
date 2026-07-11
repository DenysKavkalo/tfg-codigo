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
  width = 1200,
  height = 800
)
par(mfrow = c(ceiling(length(unique(reviews$platform)) / 2), 2), mar = c(4, 4, 3, 1))
for (platform in sort(unique(reviews$platform))) {
  scores <- reviews$rating_scaled_0_10[reviews$platform == platform]
  hist(
    scores,
    breaks = seq(0, 10, by = 1),
    main = platform,
    xlab = "Puntuacion escalada 0-10",
    ylab = "Frecuencia",
    col = "#9ecae1",
    border = "white",
    xlim = c(0, 10)
  )
}
dev.off()

png(
  filename = file.path(output_dir, "boxplot_by_platform.png"),
  width = 1000,
  height = 700
)
boxplot(
  rating_scaled_0_10 ~ platform,
  data = reviews,
  ylab = "Puntuacion escalada 0-10",
  xlab = "Plataforma",
  col = "#c7e9c0",
  border = "#238b45"
)
dev.off()

message("Analisis descriptivo escrito en ", output_dir)
