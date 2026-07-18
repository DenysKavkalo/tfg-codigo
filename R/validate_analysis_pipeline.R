#!/usr/bin/env Rscript

script_argument <- grep("^--file=", commandArgs(), value = TRUE)
script_path <- if (length(script_argument) > 0) {
  normalizePath(sub("^--file=", "", script_argument[[1]]))
} else {
  normalizePath("R/validate_analysis_pipeline.R")
}
script_dir <- dirname(script_path)
source(file.path(script_dir, "partition_model.R"))

run_script <- function(rscript, script, arguments) {
  status <- system2(
    rscript,
    args = c(script, arguments),
    stdout = TRUE,
    stderr = TRUE
  )
  exit_status <- attr(status, "status")
  if (!is.null(exit_status) && exit_status != 0) {
    stop(
      paste("Fallo al ejecutar", basename(script), paste(status, collapse = "\n")),
      call. = FALSE
    )
  }
}

expected_round <- c(0, 1, 1, 2)
scores <- c(10, 9.4, 8.6, 8.4)
if (!identical(transform_partition_scores(scores, "round"), expected_round)) {
  stop("La discretizacion half-up no supera la validacion.", call. = FALSE)
}
if (!identical(transform_partition_scores(scores, "floor"), c(0, 0, 1, 1))) {
  stop("La discretizacion floor no supera la validacion.", call. = FALSE)
}
if (!identical(transform_partition_scores(scores, "ceiling"), c(0, 1, 2, 2))) {
  stop("La discretizacion ceiling no supera la validacion.", call. = FALSE)
}

temporary_dir <- tempfile("tfg_analysis_validation_")
dir.create(temporary_dir, recursive = TRUE)
on.exit(unlink(temporary_dir, recursive = TRUE, force = TRUE), add = TRUE)

dates <- seq(as.Date("2024-01-01"), as.Date("2025-12-01"), by = "month")
platforms <- c("a", "b", "c", "d")
synthetic <- do.call(
  rbind,
  lapply(seq_along(platforms), function(index) {
    pattern <- if (index %% 2 == 0) {
      rep(c(10, 10, 10, 6), length.out = length(dates))
    } else {
      rep(c(10, 9, 8, 7), length.out = length(dates))
    }
    data.frame(
      hotel_id = "TEST_HOTEL",
      platform = platforms[[index]],
      review_date = dates,
      rating_scaled_0_10 = pattern,
      stringsAsFactors = FALSE
    )
  })
)
input_path <- file.path(temporary_dir, "synthetic_reviews.csv")
write.csv(synthetic, input_path, row.names = FALSE)

synthetic_stats <- prepare_partition_statistics(synthetic, "round")
synthetic_partitions <- analyse_partition_models(synthetic_stats)
partition_path <- file.path(temporary_dir, "synthetic_partitions.csv")
write.csv(synthetic_partitions, partition_path, row.names = FALSE)

rscript <- file.path(R.home("bin"), "Rscript.exe")
if (!file.exists(rscript)) {
  rscript <- file.path(R.home("bin"), "Rscript")
}

diagnostic_dir <- file.path(temporary_dir, "diagnostics")
run_script(
  rscript,
  file.path(script_dir, "poisson_diagnostics.R"),
  c(input_path, diagnostic_dir, "300", "1234")
)
diagnostics <- read.csv(
  file.path(diagnostic_dir, "poisson_diagnostics.csv"),
  stringsAsFactors = FALSE
)
if (nrow(diagnostics) != length(platforms)) {
  stop("El diagnostico no genera una fila por plataforma.", call. = FALSE)
}
if (!all(c("dispersion_index", "pp_dispersion_upper_p") %in% names(diagnostics))) {
  stop("Faltan indicadores del diagnostico de Poisson.", call. = FALSE)
}

frequentist_dir <- file.path(temporary_dir, "frequentist")
run_script(
  rscript,
  file.path(script_dir, "frequentist_analysis.R"),
  c(input_path, frequentist_dir, partition_path)
)
anova_results <- read.csv(
  file.path(frequentist_dir, "anova_results.csv"),
  stringsAsFactors = FALSE
)
pairwise_results <- read.csv(
  file.path(frequentist_dir, "tukey_pairwise_results.csv"),
  stringsAsFactors = FALSE
)
if (nrow(anova_results) != 2 || nrow(pairwise_results) != 6) {
  stop("El analisis frecuentista no genera las salidas previstas.", call. = FALSE)
}
if (!all(c(
  "classic_one_way_anova",
  "welch_one_way_anova"
) %in% anova_results$method)) {
  stop("Falta alguno de los contrastes ANOVA.", call. = FALSE)
}
if (any(!is.finite(anova_results$statistic_f)) ||
    any(!is.finite(pairwise_results$adjusted_p_value))) {
  stop("El analisis frecuentista contiene resultados no finitos.", call. = FALSE)
}
if (any(is.na(pairwise_results$same_dominant_bayesian_block))) {
  stop("No se ha enlazado Tukey con la particion dominante.", call. = FALSE)
}

temporal_dir <- file.path(temporary_dir, "temporal")
run_script(
  rscript,
  file.path(script_dir, "temporal_analysis.R"),
  c(input_path, temporal_dir, "2024-01-01", "2025-12-31")
)
monthly <- read.csv(
  file.path(temporal_dir, "monthly_summary.csv"),
  stringsAsFactors = FALSE
)
if (nrow(monthly) != 24 * length(platforms)) {
  stop("La rejilla temporal no contiene todos los meses.", call. = FALSE)
}

sensitivity_dir <- file.path(temporary_dir, "sensitivity")
run_script(
  rscript,
  file.path(script_dir, "sensitivity_analysis.R"),
  c(input_path, sensitivity_dir)
)
top_scenarios <- read.csv(
  file.path(sensitivity_dir, "sensitivity_top_partitions.csv"),
  stringsAsFactors = FALSE
)
key_scenarios <- read.csv(
  file.path(sensitivity_dir, "sensitivity_key_scenarios.csv"),
  stringsAsFactors = FALSE
)
all_partitions <- read.csv(
  file.path(sensitivity_dir, "sensitivity_all_partitions.csv"),
  stringsAsFactors = FALSE
)
if (nrow(top_scenarios) != 45) {
  stop("El analisis no genera los 45 escenarios previstos.", call. = FALSE)
}
if (nrow(key_scenarios) != 9) {
  stop("El resumen no contiene los nueve escenarios clave.", call. = FALSE)
}
probability_sums <- aggregate(
  posterior_probability ~ hotel_id + period_scenario + source_scenario + score_mode,
  data = all_partitions,
  FUN = sum
)
if (any(abs(probability_sums$posterior_probability - 1) > 1e-9)) {
  stop("Alguna distribucion posterior no suma uno.", call. = FALSE)
}

message(
  "Validacion integral correcta: ANOVA y Tukey, analisis temporal, ",
  "diagnostico, 24 meses y 45 escenarios de sensibilidad."
)
