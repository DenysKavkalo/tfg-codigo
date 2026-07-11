#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 2) {
  stop(
    paste(
      "Uso:",
      "Rscript R/partition_probabilities.R",
      "<summary_csv> <output_csv> [alpha] [beta]"
    ),
    call. = FALSE
  )
}

input_csv <- args[[1]]
output_csv <- args[[2]]
alpha <- if (length(args) >= 3) as.numeric(args[[3]]) else 1
beta <- if (length(args) >= 4) as.numeric(args[[4]]) else 1

required_columns <- c("platform", "n_reviews", "total_score")
summary_data <- read.csv(input_csv, stringsAsFactors = FALSE)
missing_columns <- setdiff(required_columns, names(summary_data))
if (length(missing_columns) > 0) {
  stop(
    paste("Faltan columnas obligatorias:", paste(missing_columns, collapse = ", ")),
    call. = FALSE
  )
}

if (!"hotel_id" %in% names(summary_data)) {
  summary_data$hotel_id <- "ALL"
}

summary_data <- summary_data[summary_data$n_reviews > 0, ]
if (nrow(summary_data) == 0) {
  stop("No hay plataformas con n_reviews > 0.", call. = FALSE)
}

set_partitions <- function(items) {
  if (length(items) == 0) {
    return(list(list()))
  }

  first <- items[1]
  rest <- items[-1]
  rest_partitions <- set_partitions(rest)
  output <- list()

  for (partition in rest_partitions) {
    output[[length(output) + 1]] <- c(list(c(first)), partition)

    if (length(partition) > 0) {
      for (cluster_index in seq_along(partition)) {
        updated <- partition
        updated[[cluster_index]] <- c(first, updated[[cluster_index]])
        output[[length(output) + 1]] <- updated
      }
    }
  }

  output
}

partition_label <- function(partition) {
  cluster_labels <- vapply(
    partition,
    function(cluster) paste(sort(cluster), collapse = "+"),
    character(1)
  )
  cluster_labels <- sort(cluster_labels)
  paste(cluster_labels, collapse = " | ")
}

log_cluster_marginal <- function(n_reviews, total_score, alpha, beta) {
  alpha * log(beta) -
    lgamma(alpha) +
    lgamma(alpha + total_score) -
    (alpha + total_score) * log(beta + n_reviews)
}

log_sum_exp <- function(values) {
  max_value <- max(values)
  max_value + log(sum(exp(values - max_value)))
}

analyse_hotel <- function(hotel_data) {
  platforms <- sort(unique(hotel_data$platform))
  partitions <- set_partitions(platforms)
  log_scores <- numeric(length(partitions))
  labels <- character(length(partitions))
  cluster_counts <- integer(length(partitions))

  for (partition_index in seq_along(partitions)) {
    partition <- partitions[[partition_index]]
    labels[[partition_index]] <- partition_label(partition)
    cluster_counts[[partition_index]] <- length(partition)

    cluster_log_scores <- vapply(
      partition,
      function(cluster) {
        cluster_data <- hotel_data[hotel_data$platform %in% cluster, ]
        log_cluster_marginal(
          n_reviews = sum(cluster_data$n_reviews),
          total_score = sum(cluster_data$total_score),
          alpha = alpha,
          beta = beta
        )
      },
      numeric(1)
    )

    log_scores[[partition_index]] <- sum(cluster_log_scores)
  }

  normalizer <- log_sum_exp(log_scores)
  posterior <- exp(log_scores - normalizer)

  data.frame(
    hotel_id = hotel_data$hotel_id[[1]],
    partition = labels,
    n_clusters = cluster_counts,
    log_marginal_likelihood = log_scores,
    posterior_probability = posterior,
    alpha = alpha,
    beta = beta,
    stringsAsFactors = FALSE
  )
}

results <- do.call(
  rbind,
  lapply(split(summary_data, summary_data$hotel_id), analyse_hotel)
)
results <- results[order(results$hotel_id, -results$posterior_probability), ]

output_dir <- dirname(output_csv)
if (!dir.exists(output_dir)) {
  dir.create(output_dir, recursive = TRUE)
}

write.csv(results, output_csv, row.names = FALSE)
message("Escritas ", nrow(results), " particiones en ", output_csv)
