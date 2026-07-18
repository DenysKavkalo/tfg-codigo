#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 2) {
  stop(
    paste(
      "Uso:",
      "Rscript R/frequentist_analysis.R",
      "<clean_reviews_csv> <output_dir> [partition_probabilities_csv]"
    ),
    call. = FALSE
  )
}

input_csv <- args[[1]]
output_dir <- args[[2]]
partition_csv <- if (length(args) >= 3) args[[3]] else NA_character_


run_frequentist_analysis <- function(input_csv, output_dir, partition_csv = NA_character_) {
  reviews <- read.csv(input_csv, stringsAsFactors = FALSE)
  required_columns <- c("hotel_id", "platform", "rating_scaled_0_10")
  missing_columns <- setdiff(required_columns, names(reviews))
  if (length(missing_columns) > 0) {
    stop(
      paste("Faltan columnas obligatorias:", paste(missing_columns, collapse = ", ")),
      call. = FALSE
    )
  }

  reviews <- reviews[
    !is.na(reviews$hotel_id) &
      !is.na(reviews$platform) &
      !is.na(reviews$rating_scaled_0_10),
  ]
  if (nrow(reviews) == 0) {
    stop("No hay puntuaciones validas para el analisis.", call. = FALSE)
  }
  if (any(reviews$rating_scaled_0_10 < 0 | reviews$rating_scaled_0_10 > 10)) {
    stop("Las puntuaciones deben encontrarse en la escala 0-10.", call. = FALSE)
  }

  dominant_partitions <- read_dominant_partitions(partition_csv)
  anova_rows <- list()
  pairwise_rows <- list()

  for (hotel_id in sort(unique(reviews$hotel_id))) {
    hotel_reviews <- reviews[reviews$hotel_id == hotel_id, ]
    hotel_reviews$platform <- factor(hotel_reviews$platform)
    group_sizes <- table(hotel_reviews$platform)
    if (length(group_sizes) < 2 || any(group_sizes < 2)) {
      stop(
        paste("Cada hotel necesita al menos dos grupos con dos observaciones."),
        call. = FALSE
      )
    }

    model <- aov(rating_scaled_0_10 ~ platform, data = hotel_reviews)
    classic <- summary(model)[[1]]
    between_sum_squares <- classic["platform", "Sum Sq"]
    total_sum_squares <- sum(classic[, "Sum Sq"])
    eta_squared <- between_sum_squares / total_sum_squares

    anova_rows[[length(anova_rows) + 1]] <- data.frame(
      hotel_id = hotel_id,
      method = "classic_one_way_anova",
      n_reviews = nrow(hotel_reviews),
      n_groups = nlevels(hotel_reviews$platform),
      statistic_f = classic["platform", "F value"],
      df_numerator = classic["platform", "Df"],
      df_denominator = classic["Residuals", "Df"],
      p_value = classic["platform", "Pr(>F)"],
      eta_squared = eta_squared,
      reject_equal_means_0_05 = classic["platform", "Pr(>F)"] < 0.05,
      stringsAsFactors = FALSE
    )

    welch <- oneway.test(
      rating_scaled_0_10 ~ platform,
      data = hotel_reviews,
      var.equal = FALSE
    )
    anova_rows[[length(anova_rows) + 1]] <- data.frame(
      hotel_id = hotel_id,
      method = "welch_one_way_anova",
      n_reviews = nrow(hotel_reviews),
      n_groups = nlevels(hotel_reviews$platform),
      statistic_f = unname(welch$statistic),
      df_numerator = unname(welch$parameter[[1]]),
      df_denominator = unname(welch$parameter[[2]]),
      p_value = welch$p.value,
      eta_squared = NA_real_,
      reject_equal_means_0_05 = welch$p.value < 0.05,
      stringsAsFactors = FALSE
    )

    dominant_partition <- dominant_partitions[[hotel_id]]
    tukey <- as.data.frame(TukeyHSD(model, "platform")$platform)
    tukey$comparison <- rownames(tukey)
    rownames(tukey) <- NULL
    group_means <- tapply(
      hotel_reviews$rating_scaled_0_10,
      hotel_reviews$platform,
      mean
    )

    for (index in seq_len(nrow(tukey))) {
      pair <- strsplit(tukey$comparison[[index]], "-", fixed = TRUE)[[1]]
      platform_1 <- pair[[1]]
      platform_2 <- pair[[2]]
      same_block <- if (is.na(dominant_partition)) {
        NA
      } else {
        platforms_share_block(platform_1, platform_2, dominant_partition)
      }
      difference_detected <- tukey[index, "p adj"] < 0.05

      pairwise_rows[[length(pairwise_rows) + 1]] <- data.frame(
        hotel_id = hotel_id,
        platform_1 = platform_1,
        platform_2 = platform_2,
        mean_platform_1 = unname(group_means[[platform_1]]),
        mean_platform_2 = unname(group_means[[platform_2]]),
        mean_difference_1_minus_2 = tukey[index, "diff"],
        confidence_low_95 = tukey[index, "lwr"],
        confidence_high_95 = tukey[index, "upr"],
        adjusted_p_value = tukey[index, "p adj"],
        difference_detected_0_05 = difference_detected,
        dominant_bayesian_partition = dominant_partition,
        same_dominant_bayesian_block = same_block,
        comparison_with_dominant_partition = comparison_label(
          same_block,
          difference_detected
        ),
        stringsAsFactors = FALSE
      )
    }
  }

  anova_results <- do.call(rbind, anova_rows)
  pairwise_results <- do.call(rbind, pairwise_rows)
  anova_results <- anova_results[order(anova_results$hotel_id, anova_results$method), ]
  pairwise_results <- pairwise_results[
    order(
      pairwise_results$hotel_id,
      pairwise_results$platform_1,
      pairwise_results$platform_2
    ),
  ]

  if (!dir.exists(output_dir)) {
    dir.create(output_dir, recursive = TRUE)
  }
  write.csv(
    anova_results,
    file.path(output_dir, "anova_results.csv"),
    row.names = FALSE
  )
  write.csv(
    pairwise_results,
    file.path(output_dir, "tukey_pairwise_results.csv"),
    row.names = FALSE
  )

  message(
    "Analisis frecuentista escrito en ", output_dir,
    " (", nrow(anova_results), " contrastes globales y ",
    nrow(pairwise_results), " comparaciones por pares)."
  )
}


read_dominant_partitions <- function(partition_csv) {
  if (is.na(partition_csv) || !nzchar(partition_csv)) {
    return(list())
  }
  if (!file.exists(partition_csv)) {
    stop("No se encuentra el fichero de particiones indicado.", call. = FALSE)
  }

  partitions <- read.csv(partition_csv, stringsAsFactors = FALSE)
  required_columns <- c("hotel_id", "partition", "posterior_probability")
  missing_columns <- setdiff(required_columns, names(partitions))
  if (length(missing_columns) > 0) {
    stop(
      paste(
        "Faltan columnas en el fichero de particiones:",
        paste(missing_columns, collapse = ", ")
      ),
      call. = FALSE
    )
  }

  dominant <- lapply(
    split(partitions, partitions$hotel_id),
    function(hotel) {
      hotel$partition[[which.max(hotel$posterior_probability)]]
    }
  )
  dominant
}


platforms_share_block <- function(platform_1, platform_2, partition) {
  blocks <- strsplit(partition, " | ", fixed = TRUE)[[1]]
  any(vapply(
    blocks,
    function(block) {
      members <- strsplit(block, "+", fixed = TRUE)[[1]]
      all(c(platform_1, platform_2) %in% members)
    },
    logical(1)
  ))
}


comparison_label <- function(same_block, difference_detected) {
  if (is.na(same_block)) {
    return("partition_not_provided")
  }
  if (same_block && !difference_detected) {
    return("same_block_no_difference_detected")
  }
  if (same_block && difference_detected) {
    return("same_block_difference_detected")
  }
  if (!same_block && difference_detected) {
    return("different_blocks_difference_detected")
  }
  "different_blocks_no_difference_detected"
}


run_frequentist_analysis(input_csv, output_dir, partition_csv)
