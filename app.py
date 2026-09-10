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

# 3. Panel Lateral (Sidebar) Institucional e Informativo
st.sidebar.image(
    "https://www.unl.edu.ar/servicios/wp-content/uploads/sites/62/2022/05/logo_unl.png",
    use_container_width=True,
)

st.sidebar.markdown("### 🏛️ Programa de Bibliotecas UNL")
st.sidebar.caption(
    "Herramienta institucional desarrollada por el Programa de Bibliotecas para el control2
    de calidad de la producción editorial."
)

with st.sidebar.expander("🔎 ¿Qué hace esta aplicación?", expanded=False):
  st.write(
      "Esta aplicación audita de forma automática los archivos XML exportados"
      " desde OJS antes de solicitar la activación de los identificadores"
      " persistentes (DOIs). Analiza la estructura del archivo y verifica el"
      " cumplimiento de los esquemas técnicos y buenas prácticas exigidas por"
      " Crossref."
  )

with st.sidebar.expander(
    "💡 Importancia de la curaduría de metadatos", expanded=False
):
  st.markdown("""
    Registrar metadatos completos y estandarizados no es solo un requisito administrativo, sino la base de la visibilidad científica moderna:

    * **Descubribilidad e Interconexión:** Metadatos ricos integran los artículos a la red académica global (Research Nexus), facilitando su hallazgo en bases de datos e índices internacionales.
    * **Atribución Correcta:** La inclusión de identificadores persistentes como ORCID para autores e identificadores ROR para instituciones garantiza la autoría e integridad de la filiación académica.
    * **Citación Automática y Precisión:** Evita errores en la generación de citas bibliográficas en gestores como Zotero o Mendeley al prevenir inconsistencias en títulos, volúmenes o autores.
    * **Interoperabilidad:** Permite que las computadoras y plataformas externas consuman y procesen la información de la revista de forma automatizada y abierta.
    """)

st.sidebar.divider()
st.sidebar.markdown("#### 📋 Instrucciones de Uso")
st.sidebar.info("""
1. Exporta el archivo XML desde el módulo de DOIs de OJS.
2. Carga el archivo `.xml` en el panel principal.
3. Revisa la auditoría y corrige las inconsistencias señaladas.
4. Adjunta el reporte generado en el ticket de Redmine.
""")


# 4. Funciones Auxiliares de Validación
def validar_orcid(orcid_url):
  if not orcid_url:
    return False
  pattern = (
      r"^https://orcid\.org/0000-000(1-[5-9]|2-[0-9]|3-[0-9])\d{3}-\d{3}[\dX]$"
  )
  return bool(re.match(pattern, orcid_url.strip()))


def get_tag_name(element):
  return element.tag.split("}")[-1] if "}" in element.tag else element.tag


# 5. Función Principal de Procesamiento y Auditoría
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
    if root_tag in ["issue", "articles", "native"]:
      return (
          None,
          "El XML fue generado con el 'Plugin XML Nativo' de OJS. Debes"
          " exportarlo desde el módulo de DOIs de OJS.",
      )
    return (
        None,
        "No se encontraron nodos de artículos en el XML (Nodo raíz detectado:"
        f" '{root_tag}'). Verifique que el archivo provenga del módulo de DOIs"
        " de Crossref.",
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
            "Título en MAYÚSCULAS SOSTENIDAS. Se recomienda usar mayúsculas y"
            " minúsculas estándar para facilitar la citación."
        )
      if re.search(
          r"\b(vol\.|volume|no\.|issue|pp\.|page)\b", title_text, re.IGNORECASE
      ):
        advertencias.append(
            "El título parece incluir metadatos adicionales (volumen, páginas,"
            " etc.). Sepárelos en sus etiquetas correspondientes."
        )

    # B. DOI Y URL DE DESTINO
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
      errores.append("DOI ausente o no configurado en el archivo.")
    elif not doi.startswith("10.14409/"):
      advertencias.append(
          f"El DOI registrado ('{doi}') no utiliza el prefijo institucional UNL"
          " (10.14409/)."
      )

    if not url:
      errores.append("URL de destino (resource) ausente.")
    elif not url.startswith("https://"):
      errores.append("La URL de destino no utiliza el protocolo seguro HTTPS.")

    # C. AUTORES Y CONTRIBUIDORES
    contributors = [
        e for e in art.iter() if get_tag_name(e) in ["person_name", "author"]
    ]
    autores_con_orcid = 0

    if not contributors:
      errores.append("No hay autores o contribuidores asignados al artículo.")
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

        if surname.isupper() or (given_name and given_name.isupper()):
          advertencias.append(
              f"Autor '{nombre_completo}' tiene el nombre/apellido en"
              " MAYÚSCULAS SOSTENIDAS."
          )

        if re.search(r"\b(Jr\.?|Sr\.?|II|III|IV|V)\b", surname, re.IGNORECASE):
          advertencias.append(
              f"El apellido '{surname}' incluye un sufijo. Utilice el campo"
              " dedicado <suffix>."
          )

        orcid_elem = next(
            (e for e in c.iter() if get_tag_name(e) == "ORCID"), None
        )
        if orcid_elem is None or not orcid_elem.text:
          buenas_practicas.append(
              f"Autor '{nombre_completo}' no cuenta con identificador ORCID."
          )
        else:
          orcid_val = orcid_elem.text.strip()
          if validar_orcid(orcid_val):
            autores_con_orcid += 1
          else:
            errores.append(
                f"ORCID mal formado para autor '{nombre_completo}': {orcid_val}"
            )

        affil = next(
            (
                e.text
                for e in c.iter()
                if get_tag_name(e) == "affiliation" and e.text
            ),
            None,
        )
        if not affil:
          buenas_practicas.append(
              f"Autor '{nombre_completo}' no incluye información de afiliación"
              " institucional."
          )

    # D. RESUMEN (ABSTRACT)
    abstract_elem = next(
        (e for e in art.iter() if get_tag_name(e) == "abstract"), None
    )
    tiene_abstract = abstract_elem is not None and bool(
        "".join(abstract_elem.itertext()).strip()
    )
    if not tiene_abstract:
      buenas_practicas.append("Falta el resumen (Abstract) en los metadatos.")

    # E. FECHAS DE PUBLICACIÓN
    pub_dates = [
        e
        for e in art.iter()
        if get_tag_name(e) in ["publication_date", "journal_issue"]
    ]
    for date_elem in pub_dates:
      year = next(
          (
              e.text
              for e in date_elem.iter()
              if get_tag_name(e) == "year" and e.text
          ),
          None,
      )
      month = next(
          (
              e.text
              for e in date_elem.iter()
              if get_tag_name(e) == "month" and e.text
          ),
          None,
      )
      day = next(
          (
              e.text
              for e in date_elem.iter()
              if get_tag_name(e) == "day" and e.text
          ),
          None,
      )

      if year and (not month or not day):
        buenas_practicas.append(
            "Se recomienda declarar la fecha completa de publicación (año, mes"
            " y día)."
        )
        break

    # F. PAGINACIÓN Y E-LOCATION
    first_page = next(
        (
            e.text
            for e in art.iter()
            if get_tag_name(e) == "first_page" and e.text
        ),
        None,
    )
    if first_page:
      if "-" in first_page or "–" in first_page:
        errores.append(
            f"El campo <first_page> ('{first_page}') contiene un rango. Debe"
            " incluir únicamente la página inicial."
        )
      elif re.search(r"[a-zA-Z]", first_page) and not re.match(
          r"^[eE]\d+", first_page
      ):
        advertencias.append(
            f"El campo <first_page> ('{first_page}') contiene texto"
            " innecesario."
        )

    # G. LICENCIA CC
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
      buenas_practicas.append(
          "No se declaró la licencia Creative Commons (<license_ref>)."
      )
    elif not license_elem.startswith("http"):
      advertencias.append(
          f"La URL de la licencia ('{license_elem}') no tiene un formato"
          " HTTP/HTTPS válido."
      )

    # H. REFERENCIAS ESTRUCTURADAS
    citations = [
        e
        for e in art.iter()
        if get_tag_name(e) in ["citation", "citation_list"]
    ]
    tiene_citas = len(citations) > 0
    if not tiene_citas:
      buenas_practicas.append(
          "Sin lista de referencias estructuradas (Reference Linking"
          " deshabilitado)."
      )

    # DETERMINACIÓN DE ESTADO FINAL
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
        "tiene_abstract": tiene_abstract,
        "tiene_licencia": tiene_licencia,
        "tiene_citas": tiene_citas,
    })

  return resultados, None


# --- INTERFAZ PRINCIPAL DE LA APP ---
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
    "📂 Selecciona o arrastra el archivo XML de Crossref", type=["xml"]
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
      st.error(
          f"⛔ **Lote no apto para activación:** Hay {rechazados} artículo(s) con"
          " errores críticos que rebotarán o incumplen requisitos"
          " obligatorios."
      )
    elif advertencias > 0:
      st.warning(
          f"⚠️ **Lote apto con observaciones:** {advertencias} artículo(s)"
          " tienen oportunidades de mejora en la calidad de metadatos."
      )
    else:
      st.success(
          "🎉 **Lote 100% Aprobado:** Todos los artículos cumplen con las"
          " normas técnicas y buenas prácticas."
      )

    st.divider()

    st.markdown("### 🔍 Detalle Artículo por Artículo")
    filtro = st.radio(
        "Filtrar por estado:",
        ["Todos", "🔴 Rechazados", "🟡 Con Advertencias", "🟢 Aprobados"],
        horizontal=True,
    )

    for r in resultados:
      if filtro == "🔴 Rechazados" and r["estado"] != "RECHAZADO":
        continue
      if (
          filtro == "🟡 Con Advertencias"
          and r["estado"] != "APROBADO CON ADVERTENCIAS"
      ):
        continue
      if filtro == "🟢 Aprobados" and r["estado"] != "APROBADO":
        continue

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
          st.markdown("##### ❌ Errores Críticos (Corregir obligatoriamente):")
          for err in r["errores"]:
            st.markdown(f"- 🔴 {err}")

        if r["advertencias"]:
          st.markdown("##### ⚠️ Advertencias de Calidad:")
          for adv in r["advertencias"]:
            st.markdown(f"- 🟡 {adv}")

        if r["buenas_practicas"]:
          st.markdown("##### 💡 Oportunidades de Mejora (Buenas Prácticas):")
          for bp in r["buenas_practicas"]:
            st.markdown(f"- 🔵 {bp}")

    st.divider()
    st.markdown("### 📥 Exportar Reporte de Auditoría")

    df_export = pd.DataFrame([{
        "Artículo ID": r["idx"],
        "Título": r["titulo"],
        "DOI": r["doi"],
        "Estado": r["estado"],
        "Errores Críticos": " | ".join(r["errores"]),
        "Advertencias": " | ".join(r["advertencias"]),
        "Buenas Prácticas": " | ".join(r["buenas_practicas"]),
        "Autores Con ORCID": f"{r['autores_con_orcid']}/{r['autores_total']}",
    } for r in resultados])

    csv_buffer = io.StringIO()
    df_export.to_csv(csv_buffer, index=False)

    st.download_button(
        label="📄 Descargar Reporte CSV (Para adjuntar en Redmine)",
        data=csv_buffer.getvalue(),
        file_name="reporte_auditoria_crossref.csv",
        mime="text/csv",
    )
