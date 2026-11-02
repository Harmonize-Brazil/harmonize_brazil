<p align="center">
  <img src="src/icon.png" alt="Harmonize Brazil Catalog" width="40">
</p>

<h1 align="center">Harmonize Brazil Catalog</h1>

<p align="center">
  QGIS plugin to search and download drone, health, climate and data cube data from the
  <a href="https://harmonize-brazil.github.io/">Harmonize Brazil</a> STAC catalog.
</p>

<p align="center">
  <a href="#english">English</a> · <a href="#português">Português</a>
</p>

---

## English

### Overview

**Harmonize Brazil Catalog** gives QGIS users direct access to the datasets published by the Harmonize Brazil project through its [STAC catalog](https://geolab.inpe.br/bdc/harmonize/stac/v1/collections). Users can browse the available collections, filter them by type and region, download the data for a chosen period and load it into QGIS, ready for temporal analysis.

> The plugin is under development and is currently flagged as **experimental**.

<details>
<summary><strong>Screenshots</strong></summary>

![Plugin interface](images/interface.png)

![About us window](images/about.png)

![Drone imagery loaded in QGIS](images/drone_map.png)

![Drone imagery loaded in QGIS](images/drone_RGB.png)

![Health data loaded in QGIS](images/health_data.png)

![Climate data loaded in QGIS](images/climate_data.png)

</details>

<details>
<summary><strong>Features</strong></summary>

- Browse all collections of the Harmonize Brazil STAC catalog.
- Filter by **type** (Drone, Health, Climate, Data cube), **region** (Northeast, North) and free text.
- Collection details with description, temporal extent and a link to the STAC record.
- Download by date range:
  - **Drone** imagery: GeoTIFF.
  - **Data cubes**: GeoTIFF, one band at a time.
  - **Climate and health** (municipal indicators): GeoJSON or Shapefile (zip).
- Size check before downloading, with a confirmation prompt when the total exceeds 50 MB.
- Large files are written directly to disk and downloads resume automatically after connection drops.
- Local cache: files already downloaded are reused, and interrupted downloads continue where they stopped.
- Downloads run in the background, with progress and cancellation in the QGIS task bar.
- Network access uses the QGIS network settings (proxy, SSL and authentication).
- The STAC catalog URL is read from this repository each time the catalog is loaded, so it can be changed without a new plugin release.
- Layers are loaded ready to use and configured for the **Temporal Controller**:
  - **Climate**: the same classes and colors as the project's GeoServer styles.
  - **Health**: the same colors as the project's GeoServer styles. Dengue alert levels use fixed colors (low, moderate, high and very high risk), and the other indicators use five equal-interval classes from 0 to the layer maximum.
  - **NDVI** (drone and data cubes): RdYlGn color ramp.
  - Climate and health layers have a semi-transparent fill and black outlines, so colors may look slightly different depending on the basemap.
- *About us* window with information about the Harmonize project and a link to the [Harmonize Explorer](https://geolab.inpe.br/bdc/harmonize/explorer/explore).
- Interface in **English** and **Brazilian Portuguese**, following the QGIS language setting.

</details>

<details>
<summary><strong>Available data</strong></summary>

| Type | Examples | Spatial unit | Temporal aggregation | Sources |
|---|---|---|---|---|
| Drone | RGB, multispectral and NDVI orthomosaics | Flight area | Per flight | Harmonize field campaigns |
| Health | Dengue, chikungunya, Zika, yellow fever (cases, incidence, alert level) | Municipality | Epidemiological week, month | InfoDengue, LIS |
| Climate | Precipitation, temperature, relative humidity, temperature anomalies | Municipality | Epidemiological week, month | ERA5-Land (CDS), MERGE and SAMeT (CPTEC/INPE), INMET |
| Data cube | Earth observation bands and indices | Raster grid | Cube time step | Brazil Data Cube (INPE) |

</details>

<details>
<summary><strong>Requirements</strong></summary>

- QGIS 3.22 or later.
- Internet access to `geolab.inpe.br` (data) and `raw.githubusercontent.com` (catalog configuration).

No additional Python packages are required.

</details>

<details>
<summary><strong>Installation</strong></summary>

**From a ZIP file**

1. Download the latest release from the [Releases](https://github.com/Harmonize-Brazil/harmonize_brazil/releases) page.
2. In QGIS, open *Plugins > Manage and Install Plugins > Install from ZIP*.
3. Select the file and click *Install Plugin*.
4. In the *Settings* tab, enable *Show also experimental plugins* if the plugin does not appear.

**From source (development)**

```bash
git clone https://github.com/Harmonize-Brazil/harmonize_brazil.git
```

Then create a link named `harmonize_brazil` in the QGIS plugins folder pointing to the `src` folder of the cloned repository.

Windows (Command Prompt as administrator):

```bat
mklink /D "%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\harmonize_brazil" "C:\path\to\harmonize_brazil\src"
```

Linux:

```bash
ln -s /path/to/harmonize_brazil/src ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/harmonize_brazil
```

Restart QGIS and enable the plugin. The [Plugin Reloader](https://plugins.qgis.org/plugins/plugin_reloader/) plugin is recommended for development.

</details>

<details>
<summary><strong>Usage</strong></summary>

1. Open the plugin from the toolbar icon or from *Web > Harmonize Brazil Catalog*.
2. Filter and select a collection.
3. Set the start and end dates.
4. Choose the download format (for data cubes, the band) and the output folder.
5. Click **OK**. Progress is shown in the QGIS task bar, and messages are recorded in *View > Panels > Log Messages*, tab *Harmonize Brazil*.
6. Use the **Temporal Controller** (*View > Panels > Temporal Controller*) to navigate through the loaded periods.

Downloaded files are stored in `<output folder>/<collection id>/`.

</details>

<details>
<summary><strong>Repository structure</strong></summary>

```
harmonize_brazil/
├── images/                               # Screenshots used in this README
├── src/                                  # Plugin source (installed as harmonize_brazil)
│   ├── __init__.py                       # QGIS entry point
│   ├── metadata.txt                      # Plugin metadata
│   ├── LICENSE
│   ├── harmonize_brazil.py               # Plugin class: menu, toolbar, workflow
│   ├── harmonize_brazil_dialog.py        # Dialog logic
│   ├── harmonize_brazil_dialog_base.ui   # Dialog layout (Qt Designer)
│   ├── harmonize_core.py                 # STAC access, download, layer loading and styling
│   ├── harmonize_tasks.py                # Background tasks (size check, download)
│   ├── data/harmonize_config.json        # STAC catalog URL (read from GitHub at runtime)
│   ├── i18n/                             # Translations (.ts source, .qm compiled)
│   ├── styles/                           # Climate color tables (same as GeoServer)
│   └── icon.png
├── make_zip.py                           # Builds the package for plugins.qgis.org
├── LICENSE
└── README.md
```

</details>

<details>
<summary><strong>Layer styles</strong></summary>

All styles are applied to the `value` column. Values stored as text are converted to numbers, and missing values are not drawn.

**Climate.** The files in `styles/` use the same format as the GeoServer color tables: one line per class, with the lower bound and the RGB color (`value R:G:B`). The value `-9999` marks missing data. The palette is chosen by the collection id:

| Collections | Color table |
|---|---|
| `precip_*` | `color_precipitation.txt` |
| `temp_*` | `color_temperature.txt` |
| `humidity_*` | `color_relative_humidity.txt` |
| `anomaly_*` (month) | `color_anomaly_month.txt` |
| `anomaly_*` (epiweek) | `color_anomaly_epiweek.txt` |

**Health.** Same colors as the GeoServer SLD files:

| Data | Classes |
|---|---|
| Dengue alert level | 1 Low risk (green), 2 Moderate risk (yellow), 3 High risk (orange), 4 Very high risk (red) |
| Other indicators | Five equal intervals between 0 and the layer maximum (step = maximum / 5), from light gray to dark red |

**Settings.** At the top of `harmonize_core.py`: `CLIMATE_OPACITY`, `HEALTH_OPACITY`, `CLIMATE_STROKE_COLOR`, `CLIMATE_STROKE_WIDTH`, `ALERT_LEVELS` and `HEALTH_COLORS`.

</details>

<details>
<summary><strong>Changing the STAC catalog URL</strong></summary>

The catalog URL is stored in [`src/data/harmonize_config.json`](src/data/harmonize_config.json):

```json
{
  "stac_url": "https://geolab.inpe.br/bdc/harmonize/stac/v1"
}
```

Each time the catalog is loaded, the plugin reads this file from the `main` branch of this repository. To point all users to a new catalog, edit the file and push it to `main`; no new plugin release is needed. The change may take a few minutes to reach users because of GitHub caching.

If GitHub cannot be reached within 5 seconds, or the file is invalid, the plugin uses the last valid copy it downloaded, then the copy shipped with the plugin. The URL in use and its source are recorded in the *Log Messages* panel, tab *Harmonize Brazil*.

</details>

<details>
<summary><strong>Packaging and publishing</strong></summary>

From the repository root (OSGeo4W Shell on Windows, or any Python 3):

```bash
python make_zip.py
```

The script checks the required metadata fields and files and creates `dist/harmonize_brazil-<version>.zip` with only the files needed by the plugin (Python modules, `.ui`, `metadata.txt`, `LICENSE`, `icon.png`, `i18n/*.qm`, `styles/*.txt` and `data/*.json`). Upload the zip at [plugins.qgis.org](https://plugins.qgis.org) with *Add version*, after updating `version` and `changelog` in `metadata.txt`.

</details>

<details>
<summary><strong>Translations</strong></summary>

Source strings are written in English. To update the Brazilian Portuguese translation after changing the interface or messages, run in the OSGeo4W Shell (Windows) or a terminal with Qt tools (Linux):

```bash
cd i18n
pylupdate5 -noobsolete harmonize_brazil.pro
linguist HarmonizeBrazil_pt_BR.ts
lrelease HarmonizeBrazil_pt_BR.ts
```

</details>

<details>
<summary><strong>Contributing</strong></summary>

Bug reports and suggestions are welcome in the [Issues](https://github.com/Harmonize-Brazil/harmonize_brazil/issues) page. Pull requests should describe the change and, when the interface is affected, update the translation files.

</details>

<details>
<summary><strong>About the project</strong></summary>

This work is part of the [Harmonize Project](https://www.harmonize-tools.org/): Harmonizing multi-scale spatiotemporal data for health in climate change hotspots. Harmonize is a project in partnership with the Health and Climate Observatory and several international partners, including the Barcelona Supercomputing Center (BSC).

The [Earth Observation Data Cube tuned for Health Response Systems (EODCtHRS)](https://harmonize-brazil.github.io/) component integrates climate, socioeconomic, demographic, health, disease surveillance and drone data with the digital infrastructure of the Brazil Data Cube (BDC) project of the National Institute for Space Research (INPE).

</details>

<details>
<summary><strong>Funding</strong></summary>

This work is supported by the Wellcome Trust grant number 224694/Z/21/Z.

</details>

<details>
<summary><strong>License</strong></summary>

This plugin is distributed under the [GNU General Public License v2.0 or later](LICENSE).

Data provided through the STAC catalog follow the licenses stated in each collection (most are Creative Commons Attribution 4.0 International).

</details>

---

## Português

### Visão geral

O **Harmonize Brazil Catalog** dá acesso direto, no QGIS, aos conjuntos de dados publicados pelo projeto Harmonize Brazil por meio do seu [catálogo STAC](https://geolab.inpe.br/bdc/harmonize/stac/v1/collections). É possível navegar pelas coleções, filtrá-las por tipo e região, baixar os dados de um período e carregá-los no QGIS, prontos para análise temporal.

> O plugin está em desenvolvimento e marcado como **experimental**.

<details>
<summary><strong>Funcionalidades</strong></summary>

- Navegação por todas as coleções do catálogo STAC do Harmonize Brazil.
- Filtros por **tipo** (Drone, Saúde, Clima, Cubo de dados), **região** (Nordeste, Norte) e texto livre.
- Detalhes da coleção com descrição, período disponível e link para o registro no STAC.
- Download por período:
  - Imagens de **drone**: GeoTIFF.
  - **Cubos de dados**: GeoTIFF, uma banda por vez.
  - **Clima e saúde** (indicadores municipais): GeoJSON ou Shapefile (zip).
- Verificação do tamanho antes do download, com confirmação quando o total passa de 50 MB.
- Arquivos grandes são gravados direto no disco, e o download é retomado automaticamente se a conexão cair.
- Cache local: arquivos já baixados são reaproveitados, e downloads interrompidos continuam de onde pararam.
- Downloads em segundo plano, com progresso e cancelamento pela barra de tarefas do QGIS.
- Acesso à rede pelas configurações do QGIS (proxy, SSL e autenticação).
- A URL do catálogo STAC é lida deste repositório a cada carregamento do catálogo, e pode ser alterada sem uma nova versão do plugin.
- Camadas carregadas prontas para uso e configuradas para o **Controlador Temporal**:
  - **Clima**: mesmas classes e cores dos estilos do GeoServer do projeto.
  - **Saúde**: mesmas cores dos estilos do GeoServer do projeto. O nível de alerta de dengue usa cores fixas (risco baixo, moderado, alto e muito alto), e os demais indicadores usam cinco classes de intervalos iguais entre 0 e o valor máximo da camada.
  - **NDVI** (drone e cubos de dados): rampa de cores RdYlGn.
  - As camadas de clima e saúde têm preenchimento semitransparente e contorno preto, por isso as cores podem variar um pouco conforme o mapa de fundo.
- Janela *Sobre nós* com informações sobre o projeto Harmonize e link para o [Harmonize Explorer](https://geolab.inpe.br/bdc/harmonize/explorer/explore).
- Interface em **inglês** e **português do Brasil**, conforme o idioma do QGIS.

</details>

<details>
<summary><strong>Dados disponíveis</strong></summary>

| Tipo | Exemplos | Unidade espacial | Agregação temporal | Fontes |
|---|---|---|---|---|
| Drone | Ortomosaicos RGB, multiespectrais e NDVI | Área do voo | Por voo | Campanhas de campo do Harmonize |
| Saúde | Dengue, chikungunya, Zika, febre amarela (casos, incidência, nível de alerta) | Município | Semana epidemiológica, mês | InfoDengue, LIS |
| Clima | Precipitação, temperatura, umidade relativa, anomalias de temperatura | Município | Semana epidemiológica, mês | ERA5-Land (CDS), MERGE e SAMeT (CPTEC/INPE), INMET |
| Cubo de dados | Bandas e índices de observação da Terra | Grade raster | Passo temporal do cubo | Brazil Data Cube (INPE) |

</details>

<details>
<summary><strong>Requisitos</strong></summary>

- QGIS 3.22 ou superior.
- Acesso à internet para `geolab.inpe.br` (dados) e `raw.githubusercontent.com` (configuração do catálogo).

Não é necessário instalar pacotes Python adicionais.

</details>

<details>
<summary><strong>Instalação</strong></summary>

1. Baixe a versão mais recente na página [Releases](https://github.com/Harmonize-Brazil/harmonize_brazil/releases).
2. No QGIS, abra *Complementos > Gerenciar e instalar complementos > Instalar a partir do ZIP*.
3. Selecione o arquivo e clique em *Instalar complemento*.
4. Na aba *Configurações*, marque *Mostrar também complementos experimentais* se o plugin não aparecer.

Para desenvolvimento, clone o repositório e crie, na pasta de plugins do QGIS, um link chamado `harmonize_brazil` apontando para a pasta `src`, conforme descrito na seção em inglês.

</details>

<details>
<summary><strong>Uso</strong></summary>

1. Abra o plugin pelo ícone na barra de ferramentas ou em *Web > Harmonize Brazil Catalog*.
2. Filtre e selecione uma coleção.
3. Defina as datas de início e fim.
4. Escolha o formato (nos cubos de dados, a banda) e a pasta de saída.
5. Clique em **OK**. O progresso aparece na barra de tarefas do QGIS, e as mensagens ficam em *Exibir > Painéis > Mensagens de Log*, aba *Harmonize Brazil*.
6. Use o **Controlador Temporal** (*Exibir > Painéis > Controlador Temporal*) para navegar pelos períodos carregados.

Os arquivos ficam em `<pasta de saída>/<id da coleção>/`.

</details>

<details>
<summary><strong>Estilos das camadas</strong></summary>

Os estilos são aplicados à coluna `value`. Valores gravados como texto são convertidos em número, e valores ausentes não são desenhados.

- **Clima**: tabelas de cores da pasta `styles/`, no mesmo formato do GeoServer (`valor R:G:B`), escolhidas pelo id da coleção (`precip_*`, `temp_*`, `humidity_*`, `anomaly_*`). O valor `-9999` indica ausência de dado.
- **Saúde**: nível de alerta com 1 risco baixo (verde), 2 moderado (amarelo), 3 alto (laranja) e 4 muito alto (vermelho). Os demais indicadores usam cinco intervalos iguais entre 0 e o máximo da camada (passo = máximo / 5), do cinza claro ao vermelho escuro.

Opacidade, cores e contorno são definidos no início do `harmonize_core.py`.

</details>

<details>
<summary><strong>Alterar a URL do catálogo STAC</strong></summary>

A URL fica em [`src/data/harmonize_config.json`](src/data/harmonize_config.json). A cada carregamento do catálogo, o plugin lê esse arquivo no branch `main` deste repositório. Para apontar todos os usuários para um novo catálogo, basta editar o arquivo e enviá-lo para o `main`, sem publicar nova versão do plugin. A mudança pode levar alguns minutos para chegar aos usuários por causa do cache do GitHub.

Se o GitHub não responder em 5 segundos, ou se o arquivo for inválido, o plugin usa a última cópia válida baixada e, na falta dela, a cópia distribuída com o plugin. A URL em uso e a origem ficam registradas no painel *Mensagens de Log*, aba *Harmonize Brazil*.

</details>

<details>
<summary><strong>Empacotamento e publicação</strong></summary>

Na raiz do repositório (OSGeo4W Shell no Windows, ou qualquer Python 3):

```bash
python make_zip.py
```

O script confere os campos obrigatórios do metadata e os arquivos necessários e gera `dist/harmonize_brazil-<versão>.zip` apenas com o que o plugin usa. Depois de atualizar `version` e `changelog` no `metadata.txt`, envie o zip em [plugins.qgis.org](https://plugins.qgis.org) pela opção *Add version*.

</details>

<details>
<summary><strong>Sobre o projeto</strong></summary>

Este trabalho faz parte do [Projeto Harmonize](https://www.harmonize-tools.org/), em parceria com o Observatório de Clima e Saúde e parceiros internacionais, entre eles o Barcelona Supercomputing Center (BSC). O componente [Earth Observation Data Cube tuned for Health Response Systems (EODCtHRS)](https://harmonize-brazil.github.io/) integra dados climáticos, socioeconômicos, demográficos, de saúde, de vigilância de doenças e de drone à infraestrutura do projeto Brazil Data Cube (BDC), do Instituto Nacional de Pesquisas Espaciais (INPE).

</details>

<details>
<summary><strong>Financiamento</strong></summary>

Este trabalho é financiado pelo Wellcome Trust, processo nº 224694/Z/21/Z.

</details>

<details>
<summary><strong>Licença</strong></summary>

O plugin é distribuído sob a [GNU General Public License v2.0 ou posterior](LICENSE). Os dados seguem as licenças indicadas em cada coleção do catálogo (em sua maioria, Creative Commons Attribution 4.0 International).

</details>
