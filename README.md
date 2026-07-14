# Guía de ejecución

Los comandos deben ejecutarse desde la raíz de esta carpeta.

## Requisitos

- Python 3.10 o superior.
- R con `Rscript` disponible.

Los scripts de R usan funciones base de R y no requieren paquetes adicionales.

## 1. Preparar el entorno de Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 2. Seleccionar el hotel

El flujo está preparado para los dos casos de estudio. Se debe asignar uno de los valores disponibles:

```powershell
$hotel = "venetian"  # También puede usarse "wynn"
```

Los pasos siguientes pueden repetirse cambiando el valor de `$hotel`.

## 3. Obtener las reseñas

El repositorio incluye los ficheros brutos utilizados para generar los resultados de la memoria. Para reproducir la preparación y los análisis sobre esa instantánea, puede omitirse este paso y comenzar en el apartado 4. La ejecución del comando siguiente vuelve a consultar las plataformas y sustituye el fichero bruto correspondiente, por lo que las observaciones obtenidas podrían variar.

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

## 4. Preparar los datos limpios

```powershell
python -m scraping.prepare_reviews_for_r `
  --input "data/raw/reviews_${hotel}_2024_2025_raw.csv" `
  --output "data/processed/reviews_${hotel}_2024_2025_clean.csv" `
  --summary-output "data/processed/reviews_${hotel}_2024_2025_summary.csv"
```

## 5. Análisis descriptivo en R

```powershell
Rscript R/review_distributions.R `
  "data/processed/reviews_${hotel}_2024_2025_clean.csv" `
  "data/processed/r_reviews_${hotel}_2024_2025"
```

## 6. Probabilidades de particiones en R

```powershell
Rscript R/partition_probabilities.R `
  "data/processed/reviews_${hotel}_2024_2025_clean.csv" `
  "data/processed/partition_probabilities_${hotel}_2024_2025.csv"
```

El cálculo aplica la transformación `10-S`, discretiza las puntuaciones a la
escala entera más próxima y evalúa las ecuaciones 13-15 de Martel-Escobar
et al. (2023). La implementación puede comprobarse con:

```powershell
Rscript R/validate_partition_model.R
```

Como comprobación de sensibilidad, se puede conservar el valor decimal de las
puntuaciones transformadas mediante el tercer argumento `continuous`:

```powershell
Rscript R/partition_probabilities.R `
  "data/processed/reviews_${hotel}_2024_2025_clean.csv" `
  "data/processed/partition_probabilities_${hotel}_continuous_sensitivity.csv" `
  continuous
```
