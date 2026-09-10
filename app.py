import streamlit as st
import xml.etree.ElementTree as ET
import re
import pandas as pd
import io

# Configuración de página de Streamlit
st.set_page_config(
    page_title="Validador Crossref - UNL",
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


import xml.etree.ElementTree as ET
import re
import streamlit as st

def get_tag_name(elem):
    """Elimina el namespace del tag XML si existe."""
    return elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag

def procesar_xml_crossref(xml_data):
    try:
        root = ET.fromstring(xml_data)
    except Exception as e:
        return {"error": f"Error al parsear el archivo XML: {str(e)}"}

    resumen = []
    
    # Buscar todos los artículos del archivo
    articulos = [elem for elem in root.iter() if get_tag_name(elem) == 'journal_article']

    if not articulos:
        return {"error": "No se encontraron elementos <journal_article> en el archivo XML."}

    for idx, art in enumerate(articulos, 1):
        errores = []
        advertencias = []
        buenas_practicas = []

        # ---------------------------------------------------------
        # 1. TÍTULO (Titles)
        # ---------------------------------------------------------
        titles_elem = next((e for e in art.iter() if get_tag_name(e) == 'titles'), None)
        title_text = ""
        if titles_elem is not None:
            title_node = next((e for e in titles_elem.iter() if get_tag_name(e) == 'title'), None)
            if title_node is not None and title_node.text:
                title_text = title_node.text.strip()

        if not title_text:
            errores.append("El artículo no contiene un título (<title>) obligatorio.")
        else:
            # Regla Crossref: No usar MAYÚSCULAS SOSTENIDAS en títulos
            if title_text.isupper() and len(title_text) > 5:
                advertencias.append("Título en MAYÚSCULAS SOSTENIDAS. Crossref recomienda usar mayúsculas y minúsculas estándar para facilitar la citación[cite: 2].")
            
            # Regla Crossref: No incluir metadatos ajenos en el título (volumen, páginas, autores)[cite: 2]
            if re.search(r'\b(vol\.|volume|no\.|issue|pp\.|page)\b', title_text, re.IGNORECASE):
                advertencias.append("El título parece incluir metadatos adicionales (como volúmenes o páginas). Sepárelos en sus etiquetas correspondientes[cite: 2].")

        # ---------------------------------------------------------
        # 2. DOI
        # ---------------------------------------------------------
        doi_elem = next((e for e in art.iter() if get_tag_name(e) == 'doi'), None)
        doi = doi_elem.text.strip() if doi_elem is not None and doi_elem.text else None

        if not doi:
            errores.append("No se encontró el elemento <doi> obligatorio.")
        else:
            if not doi.startswith("10.14409/"):
                advertencias.append(f"El DOI registrado ('{doi}') no utiliza el prefijo institucional UNL (10.14409/).")

        # ---------------------------------------------------------
        # 3. AUTORES Y CONTRIBUIDORES (Contributors)[cite: 2]
        # ---------------------------------------------------------
        contribs = [e for e in art.iter() if get_tag_name(e) == 'person_name']
        if not contribs:
            errores.append("No se declararon contribuidores/autores en el artículo[cite: 2].")
        else:
            for c in contribs:
                given_name = next((e.text for e in c.iter() if get_tag_name(e) == 'given_name' and e.text), "")
                surname = next((e.text for e in c.iter() if get_tag_name(e) == 'surname' and e.text), "")
                
                # Nombres o apellidos en MAYÚSCULAS SOSTENIDAS[cite: 2]
                if surname.isupper() or given_name.isupper():
                    advertencias.append(f"Autor '{given_name} {surname}' tiene el nombre/apellido en MAYÚSCULAS SOSTENIDAS[cite: 2].")
                
                # Regla Crossref: Sufijos (Jr, Sr, IV) no deben ir en el campo de apellido[cite: 2]
                if re.search(r'\b(Jr\.?|Sr\.?|II|III|IV|V)\b', surname, re.IGNORECASE):
                    advertencias.append(f"El apellido '{surname}' incluye un sufijo. Utilice el elemento dedicado <suffix>[cite: 2].")
                
                # Presencia de ORCID[cite: 2]
                orcid = next((e.text for e in c.iter() if get_tag_name(e) == 'ORCID' and e.text), None)
                if not orcid:
                    buenas_practicas.append(f"Autor '{given_name} {surname}' no incluye identificador ORCID[cite: 2].")

                # Presencia de Afiliación[cite: 2]
                affil = next((e.text for e in c.iter() if get_tag_name(e) == 'affiliation' and e.text), None)
                if not affil:
                    buenas_practicas.append(f"Autor '{given_name} {surname}' no incluye información de afiliación/institución[cite: 2].")

        # ---------------------------------------------------------
        # 4. FECHAS DE PUBLICACIÓN (Publication Dates)[cite: 2]
        # ---------------------------------------------------------
        pub_dates = [e for e in art.iter() if get_tag_name(e) in ['publication_date', 'journal_issue']]
        for date_elem in pub_dates:
            year = next((e.text for e in date_elem.iter() if get_tag_name(e) == 'year' and e.text), None)
            month = next((e.text for e in date_elem.iter() if get_tag_name(e) == 'month' and e.text), None)
            day = next((e.text for e in date_elem.iter() if get_tag_name(e) == 'day' and e.text), None)

            if year and (not month or not day):
                buenas_practicas.append("Se recomienda proporcionar la fecha completa de publicación (año, mes y día) para mayor precisión[cite: 2].")
                break

        # ---------------------------------------------------------
        # 5. PAGINACIÓN Y E-LOCATION (Pages & Article IDs)[cite: 2]
        # ---------------------------------------------------------
        first_page = next((e.text for e in art.iter() if get_tag_name(e) == 'first_page' and e.text), None)
        if first_page:
            # Regla Crossref: first_page debe incluir solo la primera página, no un rango o texto extra[cite: 2]
            if '-' in first_page or '–' in first_page:
                errores.append(f"El campo <first_page> ('{first_page}') contiene un rango. Debe incluir únicamente la página inicial[cite: 2].")
            if re.search(r'[a-zA-Z]', first_page) and not re.match(r'^[eE]\d+', first_page):
                advertencias.append(f"El campo <first_page> ('{first_page}') contiene texto innecesario. Incluya únicamente el número[cite: 2].")

        # ---------------------------------------------------------
        # 6. LICENCIA (License)[cite: 2]
        # ---------------------------------------------------------
        license_elem = next((e.text for e in art.iter() if get_tag_name(e) == 'license_ref' and e.text), None)
        if not license_elem:
            buenas_practicas.append("No se encontró información de licencia (<license_ref>). Agregar licencias facilita el reuso legítimo[cite: 2].")
        elif not license_elem.startswith("http"):
            advertencias.append(f"La URL de la licencia ('{license_elem}') no parece tener un formato HTTP/HTTPS válido[cite: 2].")

        # ---------------------------------------------------------
        # 7. REFERENCIAS (References / Citations)[cite: 2]
        # ---------------------------------------------------------
        citations = [e for e in art.iter() if get_tag_name(e) == 'citation']
        if not citations:
            buenas_practicas.append("El artículo no contiene lista de referencias bibliográficas (<citation_list>). Depositar citas mejora la visibilidad del contenido[cite: 2].")
        else:
            citations_with_doi = [c for c in citations if any(get_tag_name(child) == 'doi' for child in c.iter())]
            if len(citations_with_doi) == 0:
                buenas_practicas.append("Las citas bibliográficas declaradas no incluyen DOIs. Se recomienda adjuntar los DOIs correspondientes[cite: 2].")

        resumen.append({
            "articulo": idx,
            "titulo": title_text or "Sin título",
            "doi": doi or "Sin DOI",
            "errores": errores,
            "advertencias": advertencias,
            "buenas_practicas": buenas_practicas
        })

    return resumen
