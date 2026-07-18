#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 2) {
  stop(
    paste(
      "Uso:",
      "Rscript R/sensitivity_analysis.R",
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
  normalizePath("R/sensitivity_analysis.R")
}
source(file.path(dirname(script_path), "partition_model.R"))

run_sensitivity_analysis <- function(input_csv, output_dir) {
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
reviews$review_year <- as.integer(format(reviews$review_date, "%Y"))
reviews <- reviews[
  !is.na(reviews$review_date) & !is.na(reviews$rating_scaled_0_10),
]
if (nrow(reviews) == 0) {
  stop("No hay puntuaciones validas para el analisis.", call. = FALSE)
}

all_results <- list()
summary_rows <- list()

for (hotel_id in sort(unique(reviews$hotel_id))) {
  hotel_reviews <- reviews[reviews$hotel_id == hotel_id, ]
  platforms <- sort(unique(hotel_reviews$platform))
  periods <- c("pooled", as.character(sort(unique(hotel_reviews$review_year))))
  source_scenarios <- c("all_sources", paste0("leave_out_", platforms))
  score_modes <- c("round", "floor", "ceiling")

  reference_stats <- prepare_partition_statistics(hotel_reviews, "round")
  reference_results <- analyse_partition_models(reference_stats)
  reference_results <- reference_results[
    order(-reference_results$posterior_probability),
  ]
  reference_partition <- reference_results$partition[[1]]

  for (period_scenario in periods) {
    period_reviews <- if (period_scenario == "pooled") {
      hotel_reviews
    } else {
      hotel_reviews[hotel_reviews$review_year == as.integer(period_scenario), ]
    }

    for (source_scenario in source_scenarios) {
      excluded_platform <- if (source_scenario == "all_sources") {
        NA_character_
      } else {
        sub("^leave_out_", "", source_scenario)
      }
      scenario_reviews <- if (is.na(excluded_platform)) {
        period_reviews
      } else {
        period_reviews[period_reviews$platform != excluded_platform, ]
      }
      remaining_platforms <- sort(unique(scenario_reviews$platform))
      if (length(remaining_platforms) < 2) {
        next
      }

      projected_reference <- project_partition_label(
        reference_partition,
        remaining_platforms
      )

      for (score_mode in score_modes) {
        platform_stats <- prepare_partition_statistics(
          scenario_reviews,
          score_mode
        )
        results <- analyse_partition_models(platform_stats)
        results <- results[order(-results$posterior_probability), ]
        results$period_scenario <- period_scenario
        results$source_scenario <- source_scenario
        results$excluded_platform <- excluded_platform
        results$score_mode <- score_mode
        results$n_platforms <- length(remaining_platforms)
        results$n_reviews_scenario <- nrow(scenario_reviews)
        all_results[[length(all_results) + 1]] <- results

        probabilities <- results$posterior_probability
        entropy <- -sum(probabilities * log(probabilities))
        summary_rows[[length(summary_rows) + 1]] <- data.frame(
          hotel_id = hotel_id,
          period_scenario = period_scenario,
          source_scenario = source_scenario,
          excluded_platform = excluded_platform,
          score_mode = score_mode,
          n_platforms = length(remaining_platforms),
          n_reviews_scenario = nrow(scenario_reviews),
          reference_partition_projected = projected_reference,
          top_partition = results$partition[[1]],
          top_probability = probabilities[[1]],
          second_probability = if (length(probabilities) > 1) {
            probabilities[[2]]
          } else {
            NA_real_
          },
          normalized_entropy = if (length(probabilities) > 1) {
            entropy / log(length(probabilities))
          } else {
            0
          },
          matches_reference_structure = results$partition[[1]] == projected_reference,
          stringsAsFactors = FALSE
        )
      }
    }
  }
}

all_results_frame <- do.call(rbind, all_results)
summary_frame <- do.call(rbind, summary_rows)
all_results_frame <- all_results_frame[
  order(
    all_results_frame$hotel_id,
    all_results_frame$period_scenario,
    all_results_frame$source_scenario,
    all_results_frame$score_mode,
    -all_results_frame$posterior_probability
  ),
]
summary_frame <- summary_frame[
  order(
    summary_frame$hotel_id,
    summary_frame$period_scenario,
    summary_frame$source_scenario,
    summary_frame$score_mode
  ),
]
key_scenarios <- summary_frame[
  (summary_frame$source_scenario == "all_sources" &
    summary_frame$score_mode == "round") |
    (summary_frame$period_scenario == "pooled" &
      summary_frame$score_mode == "round") |
    (summary_frame$period_scenario == "pooled" &
      summary_frame$source_scenario == "all_sources"),
]
key_scenarios <- key_scenarios[!duplicated(key_scenarios), ]

if (!dir.exists(output_dir)) {
  dir.create(output_dir, recursive = TRUE)
}
write.csv(
  all_results_frame,
  file.path(output_dir, "sensitivity_all_partitions.csv"),
  row.names = FALSE
)
write.csv(
  summary_frame,
  file.path(output_dir, "sensitivity_top_partitions.csv"),
  row.names = FALSE
)
write.csv(
  key_scenarios,
  file.path(output_dir, "sensitivity_key_scenarios.csv"),
  row.names = FALSE
)

message(
  "Analisis de sensibilidad escrito en ", output_dir,
  " con ", nrow(summary_frame), " escenarios."
)
}


project_partition_label <- function(label, remaining_platforms) {
  clusters <- strsplit(label, " | ", fixed = TRUE)[[1]]
  projected <- lapply(
    clusters,
    function(cluster) {
      members <- strsplit(cluster, "+", fixed = TRUE)[[1]]
      intersect(members, remaining_platforms)
    }
  )
  projected <- projected[lengths(projected) > 0]
  partition_label(projected)
}


run_sensitivity_analysis(input_csv, output_dir)
