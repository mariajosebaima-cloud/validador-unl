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
