set_partitions <- function(items) {
  if (length(items) == 0) {
    return(list(list()))
  }

  first <- items[[1]]
  rest_partitions <- set_partitions(items[-1])
  output <- list()

  for (partition in rest_partitions) {
    output[[length(output) + 1]] <- c(list(first), partition)

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
  paste(sort(cluster_labels), collapse = " | ")
}

log_sum_exp <- function(values) {
  maximum <- max(values)
  maximum + log(sum(exp(values - maximum)))
}

log_homogeneity_evidence <- function(sample_sizes, totals, alpha = 0.5, beta = 0) {
  total_n <- sum(sample_sizes)
  total_score <- sum(totals)

  # Closed-form marginal evidence from equation (13).
  lgamma(total_score + alpha) -
    (total_score + alpha) * log(total_n + beta)
}

log_partition_evidence <- function(
    partition,
    platform_stats,
    alpha = 0.5,
    beta = 0,
    tail_log_tolerance = 45) {
  cluster_sizes <- vapply(
    partition,
    function(cluster) sum(platform_stats$n_reviews[match(cluster, platform_stats$platform)]),
    numeric(1)
  )
  cluster_totals <- vapply(
    partition,
    function(cluster) sum(platform_stats$total_transformed[match(cluster, platform_stats$platform)]),
    numeric(1)
  )

  # Equation (14), evaluated after the change of variable lambda = exp(u).
  log_integrand_u <- function(u) {
    vapply(
      u,
      function(value) {
        lambda <- exp(value)
        alpha * value - beta * lambda + sum(
          lgamma(cluster_totals + lambda) -
            lgamma(lambda) -
            (cluster_totals + lambda) * log(cluster_sizes + 1)
        )
      },
      numeric(1)
    )
  }

  optimum <- optimize(
    function(u) -log_integrand_u(u),
    interval = c(-20, 10)
  )
  mode_u <- optimum$minimum
  peak <- log_integrand_u(mode_u)

  lower <- mode_u
  while (lower > -40 && log_integrand_u(lower) > peak - tail_log_tolerance) {
    lower <- lower - 1
  }

  upper <- mode_u
  while (upper < 12 && log_integrand_u(upper) > peak - tail_log_tolerance) {
    upper <- upper + 1
  }

  integral <- integrate(
    function(u) exp(log_integrand_u(u) - peak),
    lower = lower,
    upper = upper,
    subdivisions = 1000L,
    rel.tol = 1e-10,
    stop.on.error = TRUE
  )

  list(
    log_evidence = peak + log(integral$value),
    scaled_integration_error = integral$abs.error,
    integration_mode_lambda = exp(mode_u)
  )
}

transform_partition_scores <- function(scores, score_mode = "round") {
  if (!score_mode %in% c("round", "floor", "ceiling")) {
    stop(
      "score_mode debe ser 'round', 'floor' o 'ceiling'.",
      call. = FALSE
    )
  }

  transformed <- 10 - scores
  if (score_mode == "round") {
    # Half-up rounding keeps the transformed scores on the Poisson support.
    return(floor(transformed + 0.5))
  }
  if (score_mode == "floor") {
    return(floor(transformed))
  }
  ceiling(transformed)
}

prepare_partition_statistics <- function(reviews, score_mode = "round") {
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
    stop("No hay puntuaciones validas para analizar.", call. = FALSE)
  }
  if (any(reviews$rating_scaled_0_10 < 0 | reviews$rating_scaled_0_10 > 10)) {
    stop("Las puntuaciones deben encontrarse en la escala 0-10.", call. = FALSE)
  }

  reviews$transformed_score <- transform_partition_scores(
    reviews$rating_scaled_0_10,
    score_mode
  )

  do.call(
    rbind,
    lapply(
      split(reviews, list(reviews$hotel_id, reviews$platform), drop = TRUE),
      function(group) {
        data.frame(
          hotel_id = group$hotel_id[[1]],
          platform = group$platform[[1]],
          n_reviews = nrow(group),
          total_transformed = sum(group$transformed_score),
          mean_transformed = mean(group$transformed_score),
          stringsAsFactors = FALSE
        )
      }
    )
  )
}

analyse_partition_models <- function(platform_stats, alpha = 0.5, beta = 0) {
  platforms <- sort(unique(platform_stats$platform))
  partitions <- set_partitions(platforms)
  log_evidence <- numeric(length(partitions))
  scaled_integration_error <- numeric(length(partitions))
  integration_mode_lambda <- numeric(length(partitions))

  for (index in seq_along(partitions)) {
    partition <- partitions[[index]]

    if (length(partition) == 1) {
      log_evidence[[index]] <- log_homogeneity_evidence(
        platform_stats$n_reviews,
        platform_stats$total_transformed,
        alpha,
        beta
      )
      scaled_integration_error[[index]] <- 0
      integration_mode_lambda[[index]] <- NA_real_
    } else {
      evidence <- log_partition_evidence(
        partition,
        platform_stats,
        alpha,
        beta
      )
      log_evidence[[index]] <- evidence$log_evidence
      scaled_integration_error[[index]] <- evidence$scaled_integration_error
      integration_mode_lambda[[index]] <- evidence$integration_mode_lambda
    }
  }

  normalizer <- log_sum_exp(log_evidence)
  homogeneity_log_evidence <- log_evidence[
    vapply(partitions, length, integer(1)) == 1
  ][[1]]

  data.frame(
    hotel_id = platform_stats$hotel_id[[1]],
    partition = vapply(partitions, partition_label, character(1)),
    n_clusters = vapply(partitions, length, integer(1)),
    log_model_evidence = log_evidence,
    log_bayes_factor_partition_vs_homogeneity =
      log_evidence - homogeneity_log_evidence,
    posterior_probability = exp(log_evidence - normalizer),
    scaled_integration_error = scaled_integration_error,
    integration_mode_lambda = integration_mode_lambda,
    alpha = alpha,
    beta = beta,
    model_prior = "uniform",
    stringsAsFactors = FALSE
  )
}
