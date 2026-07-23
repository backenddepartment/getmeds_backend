import collections
import time
import re
import httpx
from fastapi import APIRouter, Query, Response
from fastapi.responses import RedirectResponse, JSONResponse

router = APIRouter()

class BoundedCache:
    def __init__(self, maxsize=1000, ttl=3600):
        self.cache = collections.OrderedDict()
        self.maxsize = maxsize
        self.ttl = ttl
        
    def get(self, key):
        if key not in self.cache:
            return None
        timestamp, value = self.cache[key]
        if time.time() - timestamp > self.ttl:
            del self.cache[key]
            return None
        # Move to end to mark as recently used
        self.cache.move_to_end(key)
        return value
        
    def set(self, key, value):
        if key in self.cache:
            del self.cache[key]
        elif len(self.cache) >= self.maxsize:
            # Pop the oldest item
            self.cache.popitem(last=False)
        self.cache[key] = (time.time(), value)

# Cache mapping slug to boolean (True = exists, False = does not exist)
# 1 hour TTL for blog existence check
_slug_cache = BoundedCache(maxsize=2000, ttl=3600)

# Cache mapping query criteria to parsed posts list / individual post
# 10 minutes cache TTL for full blog posts/lists
_blog_cache = BoundedCache(maxsize=500, ttl=600)

WP_API_BASE = "https://cms.getmeds.ph/wp-json/wp/v2"

def clean_wordpress_url(url: str) -> str:
    if not url:
        return ""
    # Clean domains to make them root-relative paths
    for domain in ["https://cms.getmeds.ph", "https://www.getmeds.ph", "https://getmeds.ph", "http://173.231.197.156"]:
        url = url.replace(domain, "")
    return url

def parse_wp_post(item: dict) -> dict:
    # Categories tag parsing
    categories = item.get("_embedded", {}).get("wp:term", [[]])[0]
    tag = categories[0].get("name", "News") if categories else "News"
    
    # Featured image parsing
    featured_media = item.get("_embedded", {}).get("wp:featuredmedia", [{}])[0]
    image = featured_media.get("source_url", "")
    
    # Excerpt parsing & HTML stripping for clean description
    raw_excerpt = item.get("excerpt", {}).get("rendered", "")
    description = re.sub(r'<[^>]*>', '', raw_excerpt)
    description = description.replace("&amp;nbsp;", " ").replace("&nbsp;", " ")
    description = re.sub(r'&#\d+;', '', description).strip()
    
    # Read time parsing (approx 200 words per minute)
    raw_content = item.get("content", {}).get("rendered", "")
    text_only = re.sub(r'<[^>]*>', '', raw_content)
    word_count = len(text_only.split())
    minutes = max(1, round(word_count / 200))
    read_time = f"{minutes} min read"
    
    return {
        "_id": str(item.get("id", "")),
        "_type": "news",
        "tag": tag,
        "title": item.get("title", {}).get("rendered", ""),
        "slug": item.get("slug", ""),
        "date": item.get("date", ""),
        "description": description,
        "readTime": read_time,
        "image": clean_wordpress_url(image),
        "contentHtml": raw_content,
        "source_link": item.get("link", "")
    }

@router.get("/resolve-slug/{slug}")
async def resolve_slug(slug: str):
    cached_exists = _slug_cache.get(slug)
    if cached_exists is not None:
        if cached_exists:
            return RedirectResponse(url=f"/blog/{slug}", status_code=301)
        else:
            return RedirectResponse(url="/404", status_code=302)
            
    exists = False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Check WordPress API for the slug
            response = await client.get(
                f"{WP_API_BASE}/posts",
                params={"slug": slug, "_fields": "id,slug"}
            )
            if response.status_code == 200:
                posts = response.json()
                exists = len(posts) > 0
    except Exception as e:
        print(f"Error checking slug '{slug}' against WordPress API: {e}")
        # Default to False and don't cache if there was an error connecting
        return RedirectResponse(url="/404", status_code=302)
        
    _slug_cache.set(slug, exists)
    
    if exists:
        return RedirectResponse(url=f"/blog/{slug}", status_code=301)
    else:
        return RedirectResponse(url="/404", status_code=302)

@router.get("/blog/posts")
async def get_blog_posts(
    response: Response,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    slug: str = Query(default=None),
    preview: bool = Query(default=False),
    status: str = Query(default=None)
):
    cache_key = f"posts_page_{page}_per_{per_page}_slug_{slug}"
    if not preview:
        cached = _blog_cache.get(cache_key)
        if cached:
            response.headers["Cache-Control"] = "public, max-age=60, s-maxage=3600, stale-while-revalidate=600"
            return cached

    params = {"_embed": "true"}
    if slug:
        params["slug"] = slug
    else:
        params["page"] = page
        params["per_page"] = per_page

    if preview:
        params["status"] = status or "any"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            wp_res = await client.get(f"{WP_API_BASE}/posts", params=params)
            if wp_res.status_code != 200:
                return JSONResponse(status_code=wp_res.status_code, content={"error": "Failed to fetch from WordPress"})
            
            data = wp_res.json()
            total_pages = int(wp_res.headers.get("X-WP-TotalPages", 1))
            
            parsed_items = [parse_wp_post(item) for item in data]
            
            result = {
                "items": parsed_items,
                "totalPages": total_pages
            }
            
            if not preview:
                _blog_cache.set(cache_key, result)
                response.headers["Cache-Control"] = "public, max-age=60, s-maxage=3600, stale-while-revalidate=600"
            else:
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"

            return result
    except Exception as e:
        print(f"Error fetching posts: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.get("/blog/posts/{post_id}")
async def get_blog_post_by_id(post_id: int, response: Response, preview: bool = Query(default=False)):
    cache_key = f"post_id_{post_id}"
    if not preview:
        cached = _blog_cache.get(cache_key)
        if cached:
            response.headers["Cache-Control"] = "public, max-age=60, s-maxage=3600, stale-while-revalidate=600"
            return cached

    params = {"_embed": "true"}
    if preview:
        params["status"] = "any"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            wp_res = await client.get(f"{WP_API_BASE}/posts/{post_id}", params=params)
            if wp_res.status_code != 200:
                return JSONResponse(status_code=wp_res.status_code, content={"error": "Failed to fetch from WordPress"})
            
            item = wp_res.json()
            parsed_item = parse_wp_post(item)
            
            if not preview:
                _blog_cache.set(cache_key, parsed_item)
                response.headers["Cache-Control"] = "public, max-age=60, s-maxage=3600, stale-while-revalidate=600"
            else:
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"

            return parsed_item
    except Exception as e:
        print(f"Error fetching post by ID {post_id}: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
