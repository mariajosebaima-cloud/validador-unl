import io
import re
import xml.etree.ElementTree as ET
import pandas as pd
import streamlit as st

# 1. Configuración de página de Streamlit
st.set_page_config(
    page_title="Validador Crossref - UNL",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. Estilos personalizados en CSS
st.markdown(
    """
<style>
    .main-header { font-size: 2.2rem; color: #003366; font-weight: 700; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1.1rem; color: #555555; margin-bottom: 2rem; }
</style>
""",
    unsafe_allow_html=True,
)

# 3. Panel Lateral (Sidebar)
st.sidebar.image(
    "https://bibliotecas.unl.edu.ar/wp-content/uploads/2025/07/cropped-RedBibliotecas.png",
    use_container_width=True,
)
st.sidebar.caption("Aplicación desarrollada por el Programa de Bibliotecas UNL para auditoría técnica de metadatos conforme a las buenas prácticas establecidas por Crossref para registro de DOIs.")

with st.sidebar.expander("🔎 ¿Qué hace esta aplicación?", expanded=False):
  st.write(
      "Audita archivos XML exportados desde OJS verificando la presencia y"
      " calidad de los metadatos allí cargados (DOIs, ORCIDs, RORs, licencias y listas de referencias)."
  )

st.sidebar.divider()
st.sidebar.markdown("#### Instrucciones de Uso")
st.sidebar.info("""
1. Exporte el archivo XML desde el módulo de DOIs de OJS.
2. Cargue el archivo `.xml` en el validador para iniciar el diagnóstico.
3. Revise el reporte de auditoría y corrija en OJS las inconsistencias señaladas.
4. Luego de realizadas las correcciones solicitar la activación de DOIs.
""")

# 4. Funciones Auxiliares
def validar_orcid(orcid_url):
  if not orcid_url:
    return False
  pattern = (
      r"^https://orcid\.org/0000-000(1-[5-9]|2-[0-9]|3-[0-9])\d{3}-\d{3}[\dX]$"
  )
  return bool(re.match(pattern, orcid_url.strip()))


def get_tag_name(element):
  return element.tag.split("}")[-1] if "}" in element.tag else element.tag


# 5. Función Principal de Auditoría
def procesar_xml_crossref(xml_content):
  try:
    root = ET.fromstring(xml_content)
  except Exception as e:
    return None, f"Error de sintaxis XML: {str(e)}"

  articulos = [
      elem
      for elem in root.iter()
      if get_tag_name(elem) in ["journal_article", "article"]
  ]

  if not articulos:
    root_tag = get_tag_name(root)
    return (
        None,
        f"No se encontraron artículos (<journal_article>) en el XML. Nodo raíz"
        f" detectado: '{root_tag}'.",
    )

  resultados = []

  for idx, art in enumerate(articulos, 1):
    errores = []
    advertencias = []
    buenas_practicas = []

    # A. TÍTULO
    titles_elem = next(
        (e for e in art.iter() if get_tag_name(e) == "titles"), None
    )
    title_text = ""
    if titles_elem is not None:
      title_node = next(
          (e for e in titles_elem.iter() if get_tag_name(e) == "title"), None
      )
      if title_node is not None and title_node.text:
        title_text = title_node.text.strip()

    if not title_text:
      errores.append("El artículo no contiene un título (<title>) obligatorio.")
    else:
      if title_text.isupper() and len(title_text) > 5:
        advertencias.append(
            "Título en MAYÚSCULAS SOSTENIDAS. Se recomienda minúsculas"
            " estándar."
        )

    # B. DOI Y URL
    doi_elem = next((e for e in art.iter() if get_tag_name(e) == "doi"), None)
    resource_node = next(
        (e for e in art.iter() if get_tag_name(e) == "resource"), None
    )

    doi = (
        doi_elem.text.strip() if doi_elem is not None and doi_elem.text else None
    )
    url = (
        resource_node.text.strip()
        if resource_node is not None and resource_node.text
        else None
    )

    if not doi:
      errores.append("DOI ausente en los metadatos del artículo.")
    elif not doi.startswith("10.14409/"):
      advertencias.append(
          f"El DOI ('{doi}') no utiliza el prefijo institucional UNL"
          " (10.14409/)."
      )

    if not url:
      errores.append("URL de destino (resource) ausente.")
    elif not url.startswith("https://"):
      errores.append(
          f"La URL de destino ('{url}') no utiliza protocolo seguro HTTPS."
      )

    # C. AUTORES, AFILIACIONES, ORCID Y ROR
    contributors = [
        e for e in art.iter() if get_tag_name(e) in ["person_name", "author"]
    ]
    autores_con_orcid = 0
    autores_con_ror = 0

    if not contributors:
      errores.append("No hay autores asignados al artículo.")
    else:
      for c in contributors:
        given_name = next(
            (
                e.text
                for e in c.iter()
                if get_tag_name(e) == "given_name" and e.text
            ),
            "",
        )
        surname = next(
            (
                e.text
                for e in c.iter()
                if get_tag_name(e) == "surname" and e.text
            ),
            "Desconocido",
        )
        nombre_completo = f"{given_name} {surname}".strip()

        # Detección flexible de afiliación (Soporta <affiliation> e <institution_name>)
        affil_nodes = [
            e.text
            for e in c.iter()
            if get_tag_name(e) in ["affiliation", "institution_name"] and e.text
        ]
        if not affil_nodes:
          buenas_practicas.append(
              f"Autor '{nombre_completo}' no incluye afiliación institucional."
          )

        # Detección de ROR
        ror_elem = next(
            (
                e.text
                for e in c.iter()
                if get_tag_name(e) == "institution_id"
                and e.attrib.get("type") == "ror"
            ),
            None,
        )
        if ror_elem:
          autores_con_ror += 1

        # Detección de ORCID
        orcid_elem = next(
            (e for e in c.iter() if get_tag_name(e) == "ORCID"), None
        )
        if orcid_elem is None or not orcid_elem.text:
          advertencias.append(
              f"Autor '{nombre_completo}' no cuenta con ORCID registrado."
          )
        else:
          orcid_val = orcid_elem.text.strip()
          if validar_orcid(orcid_val):
            autores_con_orcid += 1
          else:
            errores.append(
                f"ORCID mal formado para autor '{nombre_completo}': {orcid_val}"
            )

      if autores_con_ror > 0:
        buenas_practicas.append(
            f"Se identificaron {autores_con_ror} autor(es) con identificador"
            " ROR de institución."
        )

    # D. RESUMEN (ABSTRACT)
    abstract_elems = [
        e for e in art.iter() if get_tag_name(e) in ["abstract", "p"]
    ]
    tiene_abstract = any(
        "".join(e.itertext()).strip() for e in abstract_elems
    )
    if not tiene_abstract:
      advertencias.append("Falta el resumen (Abstract) en los metadatos.")

    # E. LICENCIA CC
    license_elem = next(
        (
            e.text
            for e in art.iter()
            if get_tag_name(e) == "license_ref" and e.text
        ),
        None,
    )
    tiene_licencia = license_elem is not None
    if not tiene_licencia:
      advertencias.append(
          "No se declaró la licencia Creative Commons (<license_ref>)."
      )
    else:
      if license_elem.startswith("http://"):
        advertencias.append(
            f"La URL de la licencia ('{license_elem}') utiliza HTTP no seguro."
            " Se recomienda HTTPS."
        )

    # F. REFERENCIAS ESTRUCTURADAS
    citations = [
        e
        for e in art.iter()
        if get_tag_name(e) in ["citation", "citation_list"]
    ]
    tiene_citas = len(citations) > 0
    if not tiene_citas:
      advertencias.append(
          "Sin lista de referencias estructuradas (Reference Linking no"
          " disponible)."
      )

    # G. DETERMINACIÓN DE ESTADO
    if errores:
      estado = "RECHAZADO"
    elif advertencias:
      estado = "APROBADO CON ADVERTENCIAS"
    else:
      estado = "APROBADO"

    resultados.append({
        "idx": idx,
        "titulo": title_text or "Sin título",
        "doi": doi or "N/A",
        "url": url or "N/A",
        "estado": estado,
        "errores": errores,
        "advertencias": advertencias,
        "buenas_practicas": buenas_practicas,
        "autores_total": len(contributors),
        "autores_con_orcid": autores_con_orcid,
        "autores_con_ror": autores_con_ror,
        "tiene_abstract": tiene_abstract,
        "tiene_licencia": tiene_licencia,
        "tiene_citas": tiene_citas,
    })

  return resultados, None


# --- INTERFAZ PRINCIPAL ---
st.markdown(
    '<div class="main-header">Validador de Metadatos Crossref</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sub-header">Programa de Bibliotecas UNL | Auditoría técnica'
    " previa a la activación de DOIs</div>",
    unsafe_allow_html=True,
)

archivo_xml = st.file_uploader(
    "📂 Seleccione o arrastre el archivo XML de Crossref", type=["xml"]
)

if archivo_xml is not None:
  bytes_data = archivo_xml.read()
  resultados, error_msg = procesar_xml_crossref(bytes_data)

  if error_msg:
    st.error(f"❌ {error_msg}")
  else:
    total_arts = len(resultados)
    rechazados = sum(1 for r in resultados if r["estado"] == "RECHAZADO")
    advertencias = sum(
        1 for r in resultados if r["estado"] == "APROBADO CON ADVERTENCIAS"
    )
    aprobados = sum(1 for r in resultados if r["estado"] == "APROBADO")

    st.markdown("### 📊 Resumen Ejecutivo de la Auditoría")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Artículos", total_arts)
    c2.metric("🟢 Aprobados", aprobados)
    c3.metric("🟡 Con Advertencias", advertencias)
    c4.metric("🔴 Rechazados", rechazados)

    if rechazados > 0:
      st.error(f"⛔ **Lote no apto:** Se detectaron {rechazados} error(es).")
    elif advertencias > 0:
      st.warning(
          f"⚠️ **Lote apto con observaciones:** {advertencias} artículo(s)"
          " presentan observaciones de calidad."
      )
    else:
      st.success("🎉 **Lote Aprobado sin observaciones.**")

    st.divider()
    st.markdown("### 🔍 Detalle por Artículo")

    for r in resultados:
      badge = (
          "🟢 APROBADO"
          if r["estado"] == "APROBADO"
          else (
              "🟡 ADVERTENCIAS"
              if r["estado"] == "APROBADO CON ADVERTENCIAS"
              else "🔴 RECHAZADO"
          )
      )

      with st.expander(f"[{r['idx']}] {badge} — {r['titulo']}"):
        st.markdown(f"**DOI:** `{r['doi']}` | **URL:** [{r['url']}]({r['url']})")

        if r["errores"]:
          st.markdown("##### ❌ Errores Críticos:")
          for err in r["errores"]:
            st.markdown(f"- 🔴 {err}")

        if r["advertencias"]:
          st.markdown("##### ⚠️ Advertencias de Calidad:")
          for adv in r["advertencias"]:
            st.markdown(f"- 🟡 {adv}")

        if r["buenas_practicas"]:
          st.markdown("##### 💡 Observaciones / Buenas Prácticas:")
          for bp in r["buenas_practicas"]:
            st.markdown(f"- 🔵 {bp}")

    st.divider()
    df_export = pd.DataFrame([{
        "ID": r["idx"],
        "Título": r["titulo"],
        "DOI": r["doi"],
        "Estado": r["estado"],
        "Errores": " | ".join(r["errores"]),
        "Advertencias": " | ".join(r["advertencias"]),
        "Buenas Prácticas": " | ".join(r["buenas_practicas"]),
        "ORCIDs": f"{r['autores_con_orcid']}/{r['autores_total']}",
        "RORs": f"{r['autores_con_ror']}/{r['autores_total']}",
    } for r in resultados])

    csv_buffer = io.StringIO()
    df_export.to_csv(csv_buffer, index=False)
    st.download_button(
        "📄 Descargar Reporte CSV",
        csv_buffer.getvalue(),
        "reporte_crossref.csv",
        "text/csv",
    )
