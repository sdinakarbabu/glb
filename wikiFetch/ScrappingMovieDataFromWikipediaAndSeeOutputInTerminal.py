import requests
from bs4 import BeautifulSoup
import re


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def clean_reference_numbers(text):
    """Remove reference numbers in square brackets from text"""
    if not text:
        return text
    return re.sub(r'\s+', ' ', re.sub(r'\[\s*\d+\s*\]', '', text)).strip()


def is_valid_external_link(text):
    """Check if external link text is valid (not navigation elements)"""
    text_stripped = text.strip()
    nav_elements = ["v", "t", "e", "v t e", "view", "template", "edit", "talk", "history", "watch", "star", "privacy policy", "about wikipedia", "disclaimers", "contact wikipedia", "code of conduct", "developers", "statistics", "cookie statement", "mobile view"]
    return (text_stripped not in nav_elements and 
            not any(nav in text_stripped.lower() for nav in nav_elements) and
            len(text_stripped) > 1)


# =============================================================================
# EXTRACTION HELPER FUNCTIONS
# =============================================================================

def extract_plot_text(soup):
    """Extract plot text from Wikipedia page"""
    plot_h2 = soup.find("h2", {"id": "plot"}) or soup.find("h2", {"id": "Plot"})
    if not plot_h2:
        # Look for h2 containing "Plot" text
        for h2 in soup.find_all("h2"):
            if "plot" in h2.get_text(strip=True).lower() or "plot" in h2.get("id", "").lower():
                plot_h2 = h2
                break
    
    if not plot_h2:
        return ""
    
    plot_text = ""
    for p in soup.find_all("p"):
        if p.find_previous("h2") == plot_h2:
            text = clean_reference_numbers(p.get_text(separator=" ", strip=True))
            if text:
                plot_text += text + "\n"
    
    return plot_text


def extract_infobox_data(soup):
    """Extract data from Wikipedia infobox"""
    details = {}
    infobox = soup.find("table", class_="infobox")
    
    if infobox:
        infobox_mapping = {
            "directed by": "director", "director": "director",
            "produced by": "producer", "producer": "producer", 
            "written by": "writer", "screenplay": "writer",
            "music by": "music", "music": "music",
            "cinematography": "cinematography",
            "edited by": "editing", "editing": "editing",
            "production company": "production_company", "production": "production_company",
            "distributed by": "distributor",
            "release date": "release_date",
            "running time": "running_time", "duration": "running_time",
            "budget": "budget", "box office": "box_office", "gross": "box_office",
            "country": "country", "language": "language", "genre": "genre"
        }
        
        for row in infobox.find_all("tr"):
            th, td = row.find("th"), row.find("td")
            if th and td:
                key = th.get_text(strip=True).lower()
                value = clean_reference_numbers(td.get_text(separator=" ", strip=True))
                
                for pattern, field in infobox_mapping.items():
                    if pattern in key:
                        if field == "distributor" and "see below" in value.lower():
                            details[field] = "Multiple distributors (see details)"
                        else:
                            details[field] = value
                        break
    
    return details


def extract_section_data(soup, section_mappings):
    """Extract data from Wikipedia sections using provided mappings"""
    details = {}
    
    for section_id, field_name, tag in section_mappings:
        section = soup.find("h2", {"id": section_id}) or soup.find("h2", {"id": section_id.lower()})
        if section:
            items = []
            for element in section.find_all_next(tag):
                if element.find_previous("h2") == section:
                    text = clean_reference_numbers(element.get_text(separator=" ", strip=True))
                    if text and (field_name != "external_links" or is_valid_external_link(text)):
                        items.append(text)
                elif element.name == "h2":
                    break
            
            if items:
                details[field_name] = items if field_name in ["cast_details", "external_links", "references"] else "\n".join(items)
    
    return details


def extract_subsection_data(soup, subsection_mappings):
    """Extract data from Wikipedia subsections using provided mappings"""
    details = {}
    
    for section_id, field_name, tag in subsection_mappings:
        section = soup.find("h3", {"id": section_id}) or soup.find("h3", string=lambda text: text and section_id.lower().replace("_", " ") in text.lower())
        if section:
            text = ""
            for element in section.find_all_next(tag):
                if element.find_previous("h3") == section:
                    text += clean_reference_numbers(element.get_text(separator=" ", strip=True)) + "\n"
                elif element.name in ["h2", "h3"]:
                    break
            
            if text.strip():
                details[field_name] = text.strip()
    
    return details


# =============================================================================
# MAIN EXTRACTION FUNCTION
# =============================================================================

def extract_movie_details(soup):
    """Extract all movie details from Wikipedia page"""
    details = {}
    
    # Extract infobox data
    details.update(extract_infobox_data(soup))
    
    # Extract main section data
    section_mappings = [
        ("Cast", "cast_details", "li"),
        ("filming", "filming", "p"),
        ("Music", "music_details", "p"),
        ("Production", "production_details", "p"),
        ("Marketing", "marketing_details", "p"),
        ("Release", "release_details", "p"),
        ("Reception", "reception_details", "p"),
        ("External_links", "external_links", "li"),
        ("References", "references", "li")
    ]
    details.update(extract_section_data(soup, section_mappings))
    
    # Extract subsection data
    subsection_mappings = [
        ("Distribution", "distributor_details", "p"),
        ("Box_office", "box_office_details", "p"),
        ("Critical_response", "critical_response_details", "p"),
        ("Home_media", "home_media_details", "p"),
        ("Theatrical", "theatrical_details", "p"),
        ("Development", "development_details", "p"),
        ("Casting", "casting_details", "p"),
        ("Filming", "filming_details", "p")
    ]
    details.update(extract_subsection_data(soup, subsection_mappings))
    
    return details


# =============================================================================
# MAIN API FUNCTION
# =============================================================================

def get_movie_summary_wikipedia(movie_title):
    """Main function to get movie summary from Wikipedia"""
    search_title = movie_title.strip().replace(" ", "_")
    url = f"https://en.wikipedia.org/wiki/{search_title}"
    headers = {"User-Agent": "MoviePlotBot/1.0 (https://yourdomain.com; contact: you@example.com)"}
    
    print(f"Fetching: {url}")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return {"error": f"Failed to fetch page. Status code: {response.status_code}"}
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {e}"}
    
    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.find("h1").get_text(strip=True) if soup.find("h1") else movie_title
    
    # Extract plot text
    plot_text = extract_plot_text(soup)
    if not plot_text.strip():
        return {"error": "Plot section not found or empty."}
    
    # Extract movie details
    movie_details = extract_movie_details(soup)
    
    return {
        "movie_title": title,
        "url": url,
        "status": "success",
        "plot_summary": plot_text.strip(),
        **movie_details
    }


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    result = get_movie_summary_wikipedia("OG_(film)")
    print(result)