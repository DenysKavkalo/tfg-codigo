#!/usr/bin/env Rscript

script_argument <- grep("^--file=", commandArgs(), value = TRUE)
script_path <- if (length(script_argument) > 0) {
  normalizePath(sub("^--file=", "", script_argument[[1]]))
} else {
  normalizePath("R/validate_partition_model.R")
}
source(file.path(dirname(script_path), "partition_model.R"))

assert_close <- function(actual, expected, tolerance, label) {
  if (any(abs(actual - expected) > tolerance)) {
    stop(
      paste(label, "no supera la validacion.", paste(actual, collapse = ", ")),
      call. = FALSE
    )
  }
}

if (length(set_partitions(c("a", "b", "c", "d"))) != 15) {
  stop("La enumeracion de cuatro plataformas no genera 15 particiones.", call. = FALSE)
}

# Table 1 only publishes rounded means, so this check can reproduce Table 2
# approximately rather than exactly without the original individual observations.
santa_catalina <- data.frame(
  hotel_id = "SANTA_CATALINA_PUBLISHED_SUMMARY",
  platform = c("booking", "tripadvisor", "hoteles"),
  n_reviews = c(419, 206, 102),
  total_transformed = c(419, 206, 102) * (10 - c(9.14, 9.31, 9.37)),
  stringsAsFactors = FALSE
)

published_order <- c(
  "booking+hoteles+tripadvisor",
  "booking | hoteles+tripadvisor",
  "booking+hoteles | tripadvisor",
  "booking+tripadvisor | hoteles",
  "booking | hoteles | tripadvisor"
)
published_probabilities <- c(0.22, 0.57, 0.05, 0.09, 0.07)

validation <- analyse_partition_models(santa_catalina)
actual <- validation$posterior_probability[match(published_order, validation$partition)]

assert_close(sum(validation$posterior_probability), 1, 1e-10, "La suma posterior")
assert_close(actual, published_probabilities, 0.04, "La tabla publicada")

message("Validacion correcta: 15 particiones y aproximacion de la tabla publicada.")
message(
  "Probabilidades reconstruidas con medias redondeadas: ",
  paste(sprintf("%.4f", actual), collapse = ", ")
)
