import streamlit as st
import xml.etree.ElementTree as ET
import re
import pandas as pd
import io

# Configuración de página de Streamlit
st.set_page_config(
    page_title="Validador Crossref UNL",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos personalizados en CSS
st.markdown("""
<style>
    .main-header { font-size: 2.2rem; color: #003366; font-weight: 700; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1.1rem; color: #555555; margin-bottom: 2rem; }
</style>
""", unsafe_allow_html=True)

def validar_orcid(orcid_url):
    if not orcid_url:
        return False
    pattern = r'^https://orcid\.org/0000-000(1-[5-9]|2-[0-9]|3-[0-9])\d{3}-\d{3}[\dX]$'
    return bool(re.match(pattern, orcid_url.strip()))

def get_tag_name(element):
    return element.tag.split('}')[-1] if '}' in element.tag else element.tag

def procesar_xml_crossref(xml_content):
    try:
        root = ET.fromstring(xml_content)
    except Exception as e:
        return None, f"Error de sintaxis XML: {str(e)}"

    articulos = [elem for elem in root.iter() if get_tag_name(elem) == 'journal_article']
    
    if not articulos:
        return None, "No se encontraron nodos '<journal_article>' en el XML."

    resultados = []

    for idx, art in enumerate(articulos, 1):
        errores = []
        advertencias = []
        
        # 1. Título, DOI y URL
        titulo_node = next((e for e in art.iter() if get_tag_name(e) == 'title'), None)
        doi_node = next((e for e in art.iter() if get_tag_name(e) == 'doi'), None)
        resource_node = next((e for e in art.iter() if get_tag_name(e) == 'resource'), None)

        titulo = titulo_node.text.strip() if titulo_node is not None and titulo_node.text else "Sin título"
        doi = doi_node.text.strip() if doi_node is not None and doi_node.text else None
        url = resource_node.text.strip() if resource_node is not None and resource_node.text else None

        if not doi:
            errores.append("DOI ausente o no configurado.")
        if not url:
            errores.append("URL de destino (resource) ausente.")
        elif not url.startswith("https://"):
            errores.append("La URL de destino no utiliza protocolo seguro HTTPS.")

        # 2. Autores y ORCID
        contributors = [e for e in art.iter() if get_tag_name(e) == 'person_name']
        autores_con_orcid = 0

        if not contributors:
            errores.append("No hay autores asignados al artículo.")
        else:
            for c in contributors:
                given = next((e.text for e in c.iter() if get_tag_name(e) == 'given_name'), '')
                surname = next((e.text for e in c.iter() if get_tag_name(e) == 'surname'), 'Desconocido')
                nombre_completo = f"{given} {surname}".strip()
                
                orcid_elem = next((e for e in c.iter() if get_tag_name(e) == 'ORCID'), None)
                if orcid_elem is None or not orcid_elem.text:
                    advertencias.append(f"Autor '{nombre_completo}' no cuenta con ORCID.")
                else:
                    orcid_val = orcid_elem.text.strip()
                    if validar_orcid(orcid_val):
                        autores_con_orcid += 1
                    else:
                        errores.append(f"ORCID mal formado para autor '{nombre_completo}': {orcid_val}")

        # 3. Resumen
        abstract_elem = next((e for e in art.iter() if get_tag_name(e) == 'abstract'), None)
        tiene_abstract = abstract_elem is not None and bool("".join(abstract_elem.itertext()).strip())
        if not tiene_abstract:
            advertencias.append("Falta el resumen (Abstract) en los metadatos.")

        # 4. Licencia CC
        license_elem = next((e for e in art.iter() if get_tag_name(e) == 'license_ref'), None)
        tiene_licencia = license_elem is not None and bool(license_elem.text and license_elem.text.strip())
        if not tiene_licencia:
            advertencias.append("No se declaró la licencia Creative Commons (license_ref).")

        # 5. Referencias estructuradas
        citation_list = next((e for e in art.iter() if get_tag_name(e) == 'citation_list'), None)
        num_citas = len(list(citation_list)) if citation_list is not None else 0
        tiene_citas = num_citas > 0
        if not tiene_citas:
            advertencias.append("Sin lista de referencias estructuradas (Reference Linking deshabilitado).")

        # Estado Final
        if errores:
            estado = "RECHAZADO"
        elif advertencias:
            estado = "APROBADO CON ADVERTENCIAS"
        else:
            estado = "APROBADO"

        resultados.append({
            "idx": idx, "titulo": titulo, "doi": doi or "N/A", "url": url or "N/A",
            "estado": estado, "errores": errores, "advertencias": advertencias,
            "autores_total": len(contributors), "autores_con_orcid": autores_con_orcid,
            "tiene_abstract": tiene_abstract, "tiene_licencia": tiene_licencia, "tiene_citas": tiene_citas
        })

    return resultados, None

# --- INTERFAZ DE USUARIO ---
st.markdown('<div class="main-header">Validador de Metadatos Crossref</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Programa de Bibliotecas UNL | Auditoría técnica previa a la activación de DOIs</div>', unsafe_allow_html=True)

archivo_xml = st.file_uploader("📂 Selecciona o arrastra el archivo XML de Crossref", type=["xml"])

if archivo_xml is not None:
    bytes_data = archivo_xml.read()
    resultados, error_msg = procesar_xml_crossref(bytes_data)

    if error_msg:
        st.error(f"❌ {error_msg}")
    else:
        total_arts = len(resultados)
        rechazados = sum(1 for r in resultados if r["estado"] == "RECHAZADO")
        advertencias = sum(1 for r in resultados if r["estado"] == "APROBADO CON ADVERTENCIAS")
        aprobados = sum(1 for r in resultados if r["estado"] == "APROBADO")

        st.markdown("### 📊 Resumen Ejecutivo")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Artículos", total_arts)
        c2.metric("🟢 Aprobados", aprobados)
        c3.metric("🟡 Con Advertencias", advertencias)
        c4.metric("🔴 Rechazados", rechazados)

        if rechazados > 0:
            st.error(f"⛔ **Lote no apto para activación:** Hay {rechazados} artículo(s) con errores críticos.")
        else:
            st.success("🎉 **Lote Aprobado:** Todos los artículos cumplen con las normas técnicas requeridas.")

        st.divider()
        st.markdown("### 🔍 Detalle por Artículo")
        for r in resultados:
            badge = "🟢 APROBADO" if r["estado"] == "APROBADO" else ("🟡 ADVERTENCIAS" if r["estado"] == "APROBADO CON ADVERTENCIAS" else "🔴 RECHAZADO")
            with st.expander(f"[{r['idx']}] {badge} — {r['titulo']}"):
                st.markdown(f"**DOI:** `{r['doi']}` | **URL:** {r['url']}")
                for err in r["errores"]:
                    st.markdown(f"- 🔴 **Error:** {err}")
                for adv in r["advertencias"]:
                    st.markdown(f"- 🟡 **Advertencia:** {adv}")

        # Descarga de CSV
        df_export = pd.DataFrame(resultados)
        csv_buffer = io.StringIO()
        df_export.to_csv(csv_buffer, index=False)
        st.download_button("📄 Descargar Reporte CSV para Redmine", csv_buffer.getvalue(), "reporte_crossref.csv", "text/csv")
