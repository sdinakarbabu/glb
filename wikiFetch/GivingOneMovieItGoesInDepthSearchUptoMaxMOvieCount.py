import requests
from bs4 import BeautifulSoup
import re
import json
import uuid
from datetime import datetime
import os
import time

# =============================================================================
# CONFIGURATION - ALL VARIABLES IN ONE PLACE
# =============================================================================

# 🎬 MOVIE PROCESSING SETTINGS
MAX_MOVIES = 5000                # Total movies to process (5K)
START_MOVIE = "OG_(film)"           # Starting movie for discovery

# 🔗 EXTERNAL LINKS SETTINGS
PROCESS_ALL_EXTERNAL_LINKS = True   # Process ALL external links (True) or limit per movie (False)
MAX_LINKS_PER_MOVIE = 10            # Only used if PROCESS_ALL_EXTERNAL_LINKS = False

# ⏱️ PERFORMANCE & SAFETY
MAX_SAFETY_DEPTH = 20               # Hard safety limit to prevent infinite loops

# 📁 FILE SETTINGS
COMPLETED_MOVIES_FILE = "completedTestMovieList.json"
TEST_RESULTS_FILE = "testedresult.json"
MOVIE_INFO_FILE = "moviesInfoData.json"
EXTERNAL_LINKS_HISTORY_FILE = "external_links_history.json"  # Store last 100 external links

# 📚 HISTORY SETTINGS
MAX_HISTORY_LINKS = 100             # Store last 100 external links for easy tracking

# 🎯 DISCOVERY SETTINGS
ENABLE_CIRCULAR_REFERENCE_PREVENTION = True # Prevent A→B→A loops
ENABLE_GLOBAL_DUPLICATE_PREVENTION = True   # Prevent processing same movie twice

# 📊 PROGRESS MONITORING
SHOW_DETAILED_PROGRESS = True       # Show detailed progress messages
SHOW_DEPTH_INDENTATION = True       # Show depth-based indentation in logs
SHOW_SUMMARY_STATS = True           # Show success/failed/error counts

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
# EXTERNAL LINKS HISTORY MANAGEMENT
# =============================================================================

def load_external_links_history():
    """Load external links history from JSON file"""
    try:
        with open(EXTERNAL_LINKS_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"[WARNING] Error loading external links history: {e}")
        return []

def save_external_links_history(history):
    """Save external links history to JSON file"""
    try:
        with open(EXTERNAL_LINKS_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[WARNING] Error saving external links history: {e}")

def add_to_external_links_history(movie_title, external_links, depth):
    """Add external links to history (keep only last 100)"""
    try:
        history = load_external_links_history()
        
        # Add new entry
        new_entry = {
            "movie_title": movie_title,
            "external_links": external_links,
            "depth": depth,
            "timestamp": datetime.now().isoformat(),
            "link_count": len(external_links)
        }
        
        history.append(new_entry)
        
        # Keep only last MAX_HISTORY_LINKS entries
        if len(history) > MAX_HISTORY_LINKS:
            history = history[-MAX_HISTORY_LINKS:]
        
        save_external_links_history(history)
        print(f"[HISTORY] Added {len(external_links)} links from {movie_title} (depth {depth})")
        
    except Exception as e:
        print(f"[WARNING] Error adding to external links history: {e}")

def display_external_links_history():
    """Display the external links history"""
    try:
        history = load_external_links_history()
        if not history:
            print("[HISTORY] No external links history found")
            return
        
        print(f"\n📚 EXTERNAL LINKS HISTORY (Last {len(history)} entries):")
        print("=" * 80)
        
        for i, entry in enumerate(history, 1):
            print(f"{i:3d}. {entry['movie_title']} (Depth {entry['depth']}) - {entry['link_count']} links")
            print(f"     Time: {entry['timestamp']}")
            if entry['external_links']:
                print(f"     Links: {', '.join(entry['external_links'][:5])}{'...' if len(entry['external_links']) > 5 else ''}")
            print()
        
        print("=" * 80)
        
    except Exception as e:
        print(f"[ERROR] Error displaying external links history: {e}")

def clear_external_links_history():
    """Clear the external links history"""
    try:
        with open(EXTERNAL_LINKS_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
        print("[HISTORY] External links history cleared")
    except Exception as e:
        print(f"[ERROR] Error clearing external links history: {e}")

# =============================================================================
# JSON FILE MANAGEMENT FUNCTIONS
# =============================================================================

def load_completed_movies():
    """Load completed movies from JSON file"""
    try:
        return json.load(open(COMPLETED_MOVIES_FILE, "r", encoding="utf-8")) if os.path.exists(COMPLETED_MOVIES_FILE) else []
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
        
        with open(COMPLETED_MOVIES_FILE, "w", encoding="utf-8") as f:
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
        with open(COMPLETED_MOVIES_FILE, "w", encoding="utf-8") as f:
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
        
        with open(COMPLETED_MOVIES_FILE, "w", encoding="utf-8") as f:
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
        
        with open(MOVIE_INFO_FILE, "w", encoding="utf-8") as f:
            json.dump(cleaned_movie_data, f, indent=2, ensure_ascii=False)
        
        print(f"[INFO] Cleaned up moviesInfoData.json. Removed {removed_count} tracking entries.")
        return True
    except Exception as e:
        print(f"[ERROR] Error cleaning up moviesInfoData.json: {e}")
        return False


# =============================================================================
# TESTING FUNCTIONS
# =============================================================================

def extract_external_links(soup):
    """Extract external links that might be movie names"""
    external_links = []
    
    # Find external links section - try multiple approaches
    external_section = None
    
    # Try different ways to find the external links section
    for h2 in soup.find_all("h2"):
        h2_text = h2.get_text(strip=True).lower()
        h2_id = h2.get("id", "").lower()
        if "external" in h2_text or "external" in h2_id:
            external_section = h2
            break
    
    if not external_section:
        return external_links
    
    # Extract links from the external links section
    for element in external_section.find_all_next("li"):
        if element.find_previous("h2") == external_section:
            link = element.find("a")
            if link and link.get("href"):
                href = link.get("href")
                text = link.get_text(strip=True)
                
                # Check if it's a Wikipedia link and might be a movie
                if ("wikipedia.org" in href or href.startswith("/wiki/")) and is_valid_external_link(text):
                    # Extract movie title from Wikipedia URL
                    if "/wiki/" in href:
                        movie_title = href.split("/wiki/")[-1]
                        # Filter out categories and non-movie pages
                        if (movie_title and 
                            not movie_title.startswith("Category:") and 
                            not movie_title.startswith("Template:") and
                            not movie_title.startswith("Wikipedia:") and
                            not movie_title.startswith("Special:") and
                            movie_title not in external_links):
                            external_links.append(movie_title)
        elif element.name == "h2":
            break
    
    return external_links


def process_movie_recursive(movie_title, processed_movies=None, max_movies=None, visited_in_current_branch=None, recursion_depth=0, global_visited=None):
    """Recursively process movie and its external links"""
    # Use configuration defaults if not provided
    if max_movies is None:
        max_movies = MAX_MOVIES
    
    if processed_movies is None:
        processed_movies = set()
    
    if visited_in_current_branch is None:
        visited_in_current_branch = set()
    
    if global_visited is None:
        global_visited = set()
    
    # Safety check: prevent infinite recursion
    if recursion_depth > MAX_SAFETY_DEPTH:
        print(f"[SAFETY] Maximum recursion depth reached: {recursion_depth}")
        return []
    
    # Check global visited to prevent cross-branch circular references
    if movie_title in global_visited:
        print(f"[GLOBAL-SKIP] {movie_title} - already processed globally")
        return []
    
    # Stop if we've reached the maximum number of movies
    if len(processed_movies) >= max_movies:
        print(f"[LIMIT] Maximum movies reached: {max_movies}")
        return []
    
    # Prevent circular references in current branch
    if ENABLE_CIRCULAR_REFERENCE_PREVENTION and movie_title in visited_in_current_branch:
        print(f"[CIRCULAR] Skipping {movie_title} - already in current branch")
        return []
    
    # Skip if already processed globally
    if ENABLE_GLOBAL_DUPLICATE_PREVENTION and movie_title in processed_movies:
        print(f"[SKIP] {movie_title} - already processed globally")
        return []
    
    # Add to all tracking sets
    processed_movies.add(movie_title)
    visited_in_current_branch.add(movie_title)
    global_visited.add(movie_title)
    results = []
    
    print(f"\n[PROCESSING] {movie_title}")
    print(f"[PROGRESS] {len(processed_movies):,}/{max_movies:,} movies processed")
    
    # Check if movie already exists in completedTestMovieList.json
    completed_movies = load_completed_movies()
    if any(m.get("movie_title") == movie_title for m in completed_movies):
        print(f"[SKIP] {movie_title} - already processed")
        return []
    
    try:
        # Extract movie data
        result = get_movie_summary_wikipedia(movie_title)
        save_completed_movie(movie_title, result)
        
        # Create result data
        test_result = {
            "test_number": len(processed_movies), 
            "movie_title": movie_title, 
            "test_timestamp": datetime.now().isoformat(),
            "extraction_status": "success" if result.get("status") == "success" else "failed",
            "extracted_data": result,
            "depth": 0
        }
        
        movie_info_data = {"id": str(uuid.uuid4()), "movie_title": movie_title, **result}
        
        # Save test result immediately
        try:
            try:
                existing_test_data = json.load(open("testedresult.json", "r", encoding="utf-8"))
            except FileNotFoundError:
                existing_test_data = []
            
            existing_test_data.append(test_result)
            
            with open(TEST_RESULTS_FILE, "w", encoding="utf-8") as f:
                json.dump(existing_test_data, f, indent=2, ensure_ascii=False)
            
            print(f"[SAVED] testedresult.json")
            
        except Exception as e:
            print(f"[ERROR] testedresult.json: {e}")
        
        # Save movie info data immediately (only if successful)
        if result.get("status") == "success":
            try:
                try:
                    existing_movie_data = json.load(open(MOVIE_INFO_FILE, "r", encoding="utf-8"))
                except FileNotFoundError:
                    existing_movie_data = []
                
                existing_movie_data.append(movie_info_data)
                
                with open(MOVIE_INFO_FILE, "w", encoding="utf-8") as f:
                    json.dump(existing_movie_data, f, indent=2, ensure_ascii=False)
                
                print(f"[SAVED] moviesInfoData.json")
                
            except Exception as e:
                print(f"[ERROR] moviesInfoData.json: {e}")
        else:
            print(f"[SKIP] moviesInfoData.json - failed extraction")
        
        results.extend([test_result, movie_info_data])
        
        status = "SUCCESS" if result.get("status") == "success" else "FAILED"
        fields = len(result) if result.get("status") == "success" else result.get('error', 'Unknown error')
        print(f"[{status}] {fields}")
        
        # If successful, extract external links and process them recursively
        if result.get("status") == "success":
            try:
                # Re-fetch the page to get external links
                search_title = movie_title.strip().replace(" ", "_")
                url = f"https://en.wikipedia.org/wiki/{search_title}"
                headers = {"User-Agent": "MoviePlotBot/1.0 (https://yourdomain.com; contact: you@example.com)"}
                
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")
                    external_links = extract_external_links(soup)
                    
                    if external_links:
                        print(f"[FOUND] {len(external_links)} external movie links")
                        
                        # Add to external links history
                        add_to_external_links_history(movie_title, external_links, 0)
                        
                        # Process ALL external links for maximum recursive discovery
                        print(f"[PROCESSING] ALL {len(external_links)} external links")
                        
                        for i, link_movie in enumerate(external_links):
                            if link_movie not in processed_movies and len(processed_movies) < max_movies:
                                # Add small delay to prevent overwhelming Wikipedia
                                if i > 0 and i % 10 == 0:
                                    time.sleep(0.1)  # 100ms delay every 10 requests
                                
                                child_results = process_movie_recursive(
                                    link_movie, processed_movies, max_movies, visited_in_current_branch.copy(), recursion_depth + 1, global_visited
                                )
                                results.extend(child_results)
                    else:
                        print(f"[INFO] No external movie links found")
                        
            except Exception as e:
                print(f"[ERROR] Failed to extract external links: {e}")
        
        # Show summary
        completed_movies = load_completed_movies()
        successful_count = len([m for m in completed_movies if m.get("status") == "success"])
        failed_count = len([m for m in completed_movies if m.get("status") == "failed"])
        error_count = len([m for m in completed_movies if m.get("status") == "error"])
        total_count = len(completed_movies)
        
        print(f"[SUMMARY] Success: {successful_count}, Failed: {failed_count}, Errors: {error_count}, Total: {total_count}")
            
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        error_data = {"error": str(e), "status": "error"}
        save_completed_movie(movie_title, error_data)
        
        error_result = {
            "test_number": len(processed_movies), 
            "movie_title": movie_title, 
            "test_timestamp": datetime.now().isoformat(),
            "extraction_status": "error", 
            "extracted_data": error_data,
            "depth": 0
        }
        error_movie_info_data = {"id": str(uuid.uuid4()), "movie_title": movie_title, "error": str(e)}
        
        # Save error results immediately
        try:
            try:
                existing_test_data = json.load(open("testedresult.json", "r", encoding="utf-8"))
            except FileNotFoundError:
                existing_test_data = []
            
            existing_test_data.append(error_result)
            
            with open(TEST_RESULTS_FILE, "w", encoding="utf-8") as f:
                json.dump(existing_test_data, f, indent=2, ensure_ascii=False)
            
            print(f"[SAVED] testedresult.json")
            
        except Exception as e:
            print(f"[ERROR] testedresult.json: {e}")
        
        print(f"[SKIP] moviesInfoData.json - error occurred")
        
        # Show summary for error case
        completed_movies = load_completed_movies()
        successful_count = len([m for m in completed_movies if m.get("status") == "success"])
        failed_count = len([m for m in completed_movies if m.get("status") == "failed"])
        error_count = len([m for m in completed_movies if m.get("status") == "error"])
        total_count = len(completed_movies)
        
        print(f"[SUMMARY] Success: {successful_count}, Failed: {failed_count}, Errors: {error_count}, Total: {total_count}")
        
        results.extend([error_result, error_movie_info_data])
    
    # Cleanup: remove from current branch to prevent memory issues
    visited_in_current_branch.discard(movie_title)
    
    return results


def test_multiple_movies(max_movies=None, start_movie=None):
    """Large-scale movie processing with configurable limits"""
    # Use configuration defaults if not provided
    if max_movies is None:
        max_movies = MAX_MOVIES
    if start_movie is None:
        start_movie = START_MOVIE
    
    # Global visited set to prevent cross-branch circular references
    global_visited = set()
    
    print(f"🚀 Starting LARGE-SCALE movie processing")
    print(f"📊 Target: {max_movies:,} movies")
    print(f"🔗 External Links: {'ALL (unlimited)' if PROCESS_ALL_EXTERNAL_LINKS else f'Limited to {MAX_LINKS_PER_MOVIE} per movie'}")
    print(f"🎬 Starting with: {start_movie}")
    print("=" * 60)
    
    # Safety warnings
    if max_movies > 1000000:
        print("⚠️  WARNING: Processing over 1M movies may take days!")
    print("⚠️  WARNING: Processing ALL external links may be very slow!")
    print("=" * 60)
    
    # Setup and cleanup
    completed_movies = load_completed_movies()
    
    if completed_movies and any("extracted_data" in movie for movie in completed_movies):
        cleanup_completed_movies()
        completed_movies = load_completed_movies()
    
    cleanup_movies_info_data()
    
    # Start recursive processing
    start_time = datetime.now()
    results = process_movie_recursive(start_movie, max_movies=max_movies, global_visited=global_visited)
    end_time = datetime.now()
    
    # Calculate processing time
    processing_time = end_time - start_time
    hours = processing_time.total_seconds() // 3600
    minutes = (processing_time.total_seconds() % 3600) // 60
    seconds = processing_time.total_seconds() % 60
    
    # Final summary
    completed_movies = load_completed_movies()
    successful_count = len([m for m in completed_movies if m.get("status") == "success"])
    failed_count = len([m for m in completed_movies if m.get("status") == "failed"])
    error_count = len([m for m in completed_movies if m.get("status") == "error"])
    total_count = len(completed_movies)
    
    print("\n" + "=" * 60)
    print("🎉 PROCESSING COMPLETE!")
    print("=" * 60)
    print(f"📈 FINAL RESULTS:")
    print(f"   ✅ Success: {successful_count:,}")
    print(f"   ❌ Failed: {failed_count:,}")
    print(f"   ⚠️  Errors: {error_count:,}")
    print(f"   📊 Total: {total_count:,}")
    print(f"   🎯 Target: {max_movies:,}")
    print(f"   📈 Completion: {(total_count/max_movies)*100:.1f}%")
    print(f"   ⏱️  Time: {int(hours)}h {int(minutes)}m {int(seconds)}s")
    print(f"   🚀 Rate: {total_count/(processing_time.total_seconds()/60):.1f} movies/minute")
    print("=" * 60)
    
    return results


def process_movie_batch(start_movies, max_movies_per_batch=1000, max_depth=5):
    """Process multiple starting movies in batches"""
    print(f"🔄 BATCH PROCESSING MODE")
    print(f"📦 Batch Size: {max_movies_per_batch:,} movies per batch")
    print(f"🎬 Starting Movies: {len(start_movies)}")
    print("=" * 60)
    
    all_results = []
    batch_number = 1
    
    for start_movie in start_movies:
        print(f"\n🔄 BATCH {batch_number}: Starting with {start_movie}")
        print("-" * 40)
        
        # Process this batch
        batch_results = test_multiple_movies(
            max_movies=max_movies_per_batch,
            max_depth=max_depth,
            start_movie=start_movie
        )
        
        all_results.extend(batch_results)
        batch_number += 1
        
        # Show cumulative progress
        completed_movies = load_completed_movies()
        total_processed = len(completed_movies)
        print(f"\n📊 CUMULATIVE PROGRESS: {total_processed:,} movies processed")
    
    return all_results


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    # Choose your automation level:
    
    # Option 1: Small scale (1,000 movies)
    # test_multiple_movies(max_movies=1000)
    
    # Option 2: Medium scale (10,000 movies)
    # test_multiple_movies(max_movies=10000)
    
    # Option 3: Large scale (100,000 movies)
    test_multiple_movies()  # Uses MAX_MOVIES = 100000 from configuration
    
    # Option 4: Batch processing (multiple starting points)
    # start_movies = ["OG_(film)", "Baahubali:_The_Beginning", "RRR", "Pushpa:_The_Rise"]
    # process_movie_batch(start_movies, max_movies_per_batch=25000)
    
    # Option 5: Ultra large scale (1 million movies)
    # test_multiple_movies(max_movies=1000000)