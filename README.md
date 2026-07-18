# Guía de ejecución

Los comandos deben ejecutarse desde la raíz de la carpeta `Código`.

## Requisitos

- Python 3.10 o superior.
- R 4.2 o superior.

Los scripts de R utilizan únicamente funciones incluidas en la instalación base.

## 1. Preparar Python y localizar R

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

$Rscript = (Get-Command Rscript -ErrorAction SilentlyContinue).Source
if (-not $Rscript) {
  $Rscript = (Get-ChildItem "C:\Program Files\R\R-*\bin\Rscript.exe" |
    Sort-Object FullName -Descending | Select-Object -First 1).FullName
}
if (-not $Rscript) { throw "No se encontró Rscript." }
```

## 2. Seleccionar el hotel

El mismo flujo se ejecuta por separado para cada caso:

```powershell
$hotel = "venetian"  # Repetir después con "wynn"
```

## 3. Obtener las reseñas

El repositorio conserva los ficheros brutos empleados en la memoria. Para reproducir exactamente los resultados puede omitirse este paso y comenzar en el apartado 4. Una extracción nueva consulta de nuevo las fuentes y puede recuperar observaciones diferentes.

```powershell
python -m scraping.scrape_reviews_year `
  --input "data/manual/review_sources_$hotel.csv" `
  --output "data/raw/reviews_${hotel}_2024_2025_raw.csv" `
  --start-date 2024-01-01 `
  --end-date 2025-12-31 `
  --platforms tripcom agoda priceline `
  --agoda-provider-mode separate `
  --exclude-output-platforms priceline_com_via_agoda `
  --max-pages 40 `
  --delay-seconds 1
```

## 4. Preparar y validar los datos

```powershell
python -m scraping.prepare_reviews_for_r `
  --input "data/raw/reviews_${hotel}_2024_2025_raw.csv" `
  --output "data/processed/reviews_${hotel}_2024_2025_clean.csv" `
  --summary-output "data/processed/reviews_${hotel}_2024_2025_summary.csv" `
  --quality-output "data/processed/reviews_${hotel}_2024_2025_quality.csv"
```

## 5. Ejecutar los análisis en R

```powershell
$clean = "data/processed/reviews_${hotel}_2024_2025_clean.csv"
$results = "data/processed/r_reviews_${hotel}_2024_2025"

& $Rscript R/review_distributions.R $clean $results

& $Rscript R/partition_probabilities.R `
  $clean "data/processed/partition_probabilities_${hotel}_2024_2025.csv" round

& $Rscript R/frequentist_analysis.R `
  $clean $results "data/processed/partition_probabilities_${hotel}_2024_2025.csv"

& $Rscript R/poisson_diagnostics.R $clean $results 5000 20240601
& $Rscript R/temporal_analysis.R $clean $results 2024-01-01 2025-12-31
& $Rscript R/sensitivity_analysis.R $clean $results
```

El análisis de sensibilidad genera 45 escenarios por hotel: periodo completo, 2024 y 2025; todas las fuentes y cuatro exclusiones individuales; y discretización mediante redondeo, suelo y techo.

## 6. Ejecutar las pruebas

```powershell
python -m unittest discover -s tests -v
& $Rscript R/validate_partition_model.R
& $Rscript R/validate_analysis_pipeline.R
```

La primera validación contrasta la implementación de las particiones con los resultados publicados por Martel--Escobar et al. (2023). La segunda comprueba ANOVA y Tukey, la transformación de puntuaciones, el diagnóstico de Poisson, la rejilla de 24 meses, los 45 escenarios y la suma unitaria de cada distribución posterior.

El navegador automatizado es opcional y no interviene en la ejecución anterior. La opción `--render-js` solo puede utilizarse con páginas solicitadas mediante GET; no es compatible con los endpoints POST de Agoda y Trip.com. Para habilitarla se requiere instalar Playwright mediante `python -m pip install playwright` y `python -m playwright install chromium`.
