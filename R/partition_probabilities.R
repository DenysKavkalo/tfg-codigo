#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 2) {
  stop(
    paste(
      "Uso:",
      "Rscript R/partition_probabilities.R",
      "<clean_reviews_csv> <output_csv> [round|floor|ceiling]"
    ),
    call. = FALSE
  )
}

input_csv <- args[[1]]
output_csv <- args[[2]]
score_mode <- if (length(args) >= 3) args[[3]] else "round"

script_argument <- grep("^--file=", commandArgs(), value = TRUE)
script_path <- if (length(script_argument) > 0) {
  normalizePath(sub("^--file=", "", script_argument[[1]]))
} else {
  normalizePath("R/partition_probabilities.R")
}
source(file.path(dirname(script_path), "partition_model.R"))

reviews <- read.csv(input_csv, stringsAsFactors = FALSE)
platform_stats <- prepare_partition_statistics(reviews, score_mode)

results <- do.call(
  rbind,
  lapply(
    split(platform_stats, platform_stats$hotel_id),
    analyse_partition_models
  )
)
results$score_transform <- "10-rating_scaled_0_10"
results$score_mode <- score_mode
results$model <- "Martel-Escobar et al. (2023), equations 13-15"
results <- results[order(results$hotel_id, -results$posterior_probability), ]

output_dir <- dirname(output_csv)
if (!dir.exists(output_dir)) {
  dir.create(output_dir, recursive = TRUE)
}

write.csv(results, output_csv, row.names = FALSE)
message(
  "Escritas ", nrow(results), " particiones en ", output_csv,
  " (transformacion 10-S; modo ", score_mode, ")."
)
