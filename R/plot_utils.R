platform_display_name <- function(platforms) {
  labels <- c(
    agoda = "Agoda",
    booking_via_agoda = "Booking.com v\u00eda Agoda",
    priceline = "Priceline",
    tripcom = "Trip.com"
  )
  output <- unname(labels[platforms])
  output[is.na(output)] <- platforms[is.na(output)]
  output
}
