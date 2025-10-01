import requests
from bs4 import BeautifulSoup
import re
import json
import uuid
from datetime import datetime
import os


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
# WIKIPEDIA EXTRACTION FUNCTIONS
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


def extract_movie_details(soup):
    """Extract all movie details from Wikipedia page"""
    details = {}
    
    # Extract infobox data
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
    
    # Extract section data using helper function
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
# JSON FILE MANAGEMENT FUNCTIONS
# =============================================================================

def load_completed_movies():
    """Load completed movies from JSON file"""
    try:
        return json.load(open("completedTestMovieList.json", "r", encoding="utf-8")) if os.path.exists("completedTestMovieList.json") else []
    except Exception as e:
        print(f"[WARNING] Error loading completed movies: {e}")
        return []


def save_completed_movie(movie_title, movie_data):
    """Save completed movie to JSON file"""
    try:
        completed_movies = load_completed_movies()
        existing_movie = next((m for m in completed_movies if m.get("movie_title") == movie_title), None)
        
        movie_info = {
            "id": str(uuid.uuid4()),
            "movie_title": movie_title,
            "completion_timestamp": datetime.now().isoformat(),
            "status": "success" if movie_data.get("status") == "success" else "failed",
            "error": movie_data.get("error") if movie_data.get("status") != "success" else None
        }
        
        if existing_movie:
            existing_movie.update(movie_info)
        else:
            completed_movies.append(movie_info)
        
        with open("completedTestMovieList.json", "w", encoding="utf-8") as f:
            json.dump(completed_movies, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ERROR] Error saving completed movie: {e}")
        return False


# =============================================================================
# MOVIE STATUS CHECKING FUNCTIONS
# =============================================================================

def is_movie_completed(movie_title):
    """Check if movie is already completed successfully"""
    return any(m.get("movie_title") == movie_title and m.get("status") == "success" for m in load_completed_movies())


def get_completed_movie_data(movie_title):
    """Get data for completed movie"""
    return next((m for m in load_completed_movies() if m.get("movie_title") == movie_title), None)


# =============================================================================
# DISPLAY AND UTILITY FUNCTIONS
# =============================================================================

def display_completed_movies():
    """Display list of completed movies"""
    completed_movies = load_completed_movies()
    if not completed_movies:
        print("[INFO] No completed movies found.")
        return
    
    print(f"\n[COMPLETED MOVIES] Found {len(completed_movies)} completed movies:")
    print("-" * 60)
    for movie in completed_movies:
        status_icon = "✓" if movie.get("status") == "success" else "✗"
        print(f"{status_icon} {movie.get('movie_title', 'Unknown')} - {movie.get('status', 'Unknown')} ({movie.get('completion_timestamp', 'Unknown')})")
    print("-" * 60)


def clear_completed_movies():
    """Clear completed movies list"""
    try:
        with open("completedTestMovieList.json", "w", encoding="utf-8") as f:
            json.dump([], f, indent=2, ensure_ascii=False)
        print("[INFO] Completed movies list cleared.")
        return True
    except Exception as e:
        print(f"[ERROR] Error clearing completed movies list: {e}")
        return False


# =============================================================================
# CLEANUP FUNCTIONS
# =============================================================================

def cleanup_completed_movies():
    """Remove extracted_data from completed movies list"""
    try:
        completed_movies = load_completed_movies()
        cleaned_movies = [{"id": m.get("id"), "movie_title": m.get("movie_title"), 
                          "completion_timestamp": m.get("completion_timestamp"), 
                          "status": m.get("status"), "error": m.get("error")} for m in completed_movies]
        
        with open("completedTestMovieList.json", "w", encoding="utf-8") as f:
            json.dump(cleaned_movies, f, indent=2, ensure_ascii=False)
        
        print(f"[INFO] Cleaned up completed movies list. Removed extracted_data from {len(completed_movies)} movies.")
        return True
    except Exception as e:
        print(f"[ERROR] Error cleaning up completed movies list: {e}")
        return False


def cleanup_movies_info_data():
    """Remove tracking entries from moviesInfoData.json"""
    try:
        try:
            movie_data = json.load(open("moviesInfoData.json", "r", encoding="utf-8"))
        except FileNotFoundError:
            print("[INFO] moviesInfoData.json not found.")
            return True
        
        cleaned_movie_data = []
        removed_count = 0
        
        for movie in movie_data:
            if ("completion_timestamp" in movie and "status" in movie and 
                "plot_summary" not in movie and len(movie) <= 5):
                removed_count += 1
                print(f"[REMOVED] Tracking entry for: {movie.get('movie_title', 'Unknown')}")
            else:
                cleaned_movie_data.append(movie)
        
        with open("moviesInfoData.json", "w", encoding="utf-8") as f:
            json.dump(cleaned_movie_data, f, indent=2, ensure_ascii=False)
        
        print(f"[INFO] Cleaned up moviesInfoData.json. Removed {removed_count} tracking entries.")
        return True
    except Exception as e:
        print(f"[ERROR] Error cleaning up moviesInfoData.json: {e}")
        return False


# =============================================================================
# TESTING FUNCTIONS
# =============================================================================

def test_multiple_movies():
    """Test movies and save results to JSON files"""
    test_movies = ["OG_(film)", "Baahubali:_The_Beginning"]
    results, skipped_movies = [], []
    
    print("Testing movies...\n" + "=" * 50)
    
    # Setup and cleanup
    completed_movies = load_completed_movies()
    print(f"[INFO] Found {len(completed_movies)} previously completed movies")
    
    if completed_movies and any("extracted_data" in movie for movie in completed_movies):
        print("[INFO] Cleaning up completed movies list...")
        cleanup_completed_movies()
        completed_movies = load_completed_movies()
    
    print("[INFO] Cleaning up moviesInfoData.json...")
    cleanup_movies_info_data()
    display_completed_movies()
    
    # Process movies
    for i, movie in enumerate(test_movies, 1):
        print(f"[{i}/{len(test_movies)}] Testing: {movie}")
        
        if is_movie_completed(movie):
            print(f"  [SKIP] Movie already completed - skipping")
            skipped_movies.append(movie)
            continue
        
        try:
            result = get_movie_summary_wikipedia(movie)
            save_completed_movie(movie, result)
            
            # Create result data
            test_result = {
                "test_number": i, "movie_title": movie, "test_timestamp": datetime.now().isoformat(),
                "extraction_status": "success" if result.get("status") == "success" else "failed",
                "extracted_data": result
            }
            
            movie_info_data = {"id": str(uuid.uuid4()), "movie_title": movie, **result}
            
            results.extend([test_result, movie_info_data])
            
            status = "OK" if result.get("status") == "success" else "FAIL"
            message = f"Success - {len(result)} fields extracted" if result.get("status") == "success" else f"Failed - {result.get('error', 'Unknown error')}"
            print(f"  [{status}] {message}")
                
        except Exception as e:
            print(f"  [ERROR] Error: {str(e)}")
            error_data = {"error": str(e), "status": "error"}
            save_completed_movie(movie, error_data)
            
            error_result = {
                "test_number": i, "movie_title": movie, "test_timestamp": datetime.now().isoformat(),
                "extraction_status": "error", "extracted_data": error_data
            }
            error_movie_info_data = {"id": str(uuid.uuid4()), "movie_title": movie, "error": str(e)}
            results.extend([error_result, error_movie_info_data])
    
    # Save results
    test_results = [r for r in results if "test_number" in r]
    movie_info_data = [r for r in results if "id" in r]
    
    # Save to JSON files
    for filename, data in [("testedresult.json", test_results), ("moviesInfoData.json", movie_info_data)]:
        try:
            try:
                existing_data = json.load(open(filename, "r", encoding="utf-8"))
            except FileNotFoundError:
                existing_data = []
            
            existing_data.extend(data)
            
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)
            
            print(f"\n[OK] {filename} saved - Total records: {len(existing_data)}")
            
        except Exception as e:
            print(f"[ERROR] Error saving {filename}: {e}")
    
    # Print summary
    successful = len([r for r in test_results if r["extraction_status"] == "success"])
    failed = len([r for r in test_results if r["extraction_status"] == "failed"])
    errors = len([r for r in test_results if r["extraction_status"] == "error"])
    skipped = len(skipped_movies)
    
    print(f"[BATCH] This batch: {successful} success, {failed} failed, {errors} errors, {skipped} skipped")
    if skipped_movies:
        print(f"[SKIPPED] Movies: {', '.join(skipped_movies)}")
    
    return results


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    test_multiple_movies()