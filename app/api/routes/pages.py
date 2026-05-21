import re
from fastapi import APIRouter, HTTPException
from app.services.sanity_service import sanity_service

router = APIRouter()

# Map page names to Sanity document type and fixed singleton ID (excluding footer & navigation which are dynamic)
PAGE_MAPPINGS = {
    "about": {"type": "aboutPage", "id": "about-page"},
    "careers": {"type": "careersPage", "id": "careers-page"},
    "contact": {"type": "contactPage", "id": "contact-page"},
    "csr": {"type": "csrPage", "id": "csr-page"},
    "global-presence": {"type": "globalPresencePage", "id": "global-presence-page"},
    "home": {"type": "homePage", "id": "home-page"},
    "meditations": {"type": "meditationsPage", "id": "meditations-page"},
    "order-medicines": {"type": "orderMedicinesPage", "id": "order-medicines-page"},
    "pap": {"type": "papPage", "id": "pap-page"},
    "services": {"type": "servicesPage", "id": "services-page"},
    "ungc": {"type": "ungcPage", "id": "ungc-page"}
}

def slugify(text: str) -> str:
    """Helper to convert names to lowercase hyphenated slugs."""
    if not text:
        return ""
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')

def clean_sanity_document(doc):
    """
    Recursively remove Sanity-specific metadata fields like _id, _type, _rev, _createdAt, _updatedAt
    and the root-level administrative 'title' field to return pure JSON.
    """
    if not isinstance(doc, dict):
        return doc
    
    cleaned = {}
    for k, v in doc.items():
        if k.startswith('_') or k == 'title':
            continue
            
        if isinstance(v, dict):
            cleaned[k] = clean_sanity_document(v)
        elif isinstance(v, list):
            cleaned_list = []
            for item in v:
                if isinstance(item, dict):
                    cleaned_list.append(clean_sanity_document(item))
                else:
                    cleaned_list.append(item)
            cleaned[k] = cleaned_list
        else:
            cleaned[k] = v
    return cleaned

@router.get("/navigation")
async def get_navigation():
    """
    Dynamically generates the navigation configuration (navigation.json)
    by combining siteSettings (branding details) and category schemas.
    """
    try:
        # 1. Fetch site settings for the logo
        settings_query = '*[_type == "siteSettings" && _id == "global-site-settings"][0]'
        settings = await sanity_service.query_sanity(settings_query) or {}

        # 2. Fetch categories for the product range mega menu
        categories_query = '*[_type == "category"] | order(category asc)'
        categories = await sanity_service.query_sanity(categories_query) or []

        # 3. Format logo
        logo_data = settings.get("logo", {})
        logo = {
            "src": logo_data.get("src", "assets/getmedslogo.png"),
            "alt": logo_data.get("alt", "GetMEDS Logo"),
            "href": "index.html"
        }

        # 4. Define static main links
        main_links = [
            { "label": "Home", "href": "/" },
            { "label": "Order Medicines", "href": "order-medicines.html" },
            { "label": "Product Range", "href": "product-range.html", "hasDropdown": True },
            { "label": "Meditations", "href": "meditations.html" },
            { "label": "About Us", "href": "about-us.html" },
            { "label": "Contact Us", "href": "contact-us.html" },
            { "label": "Company", "href": "#", "hasDropdown": True }
        ]

        # 5. Build dynamic Product Range mega menu
        product_columns = []
        for cat in categories:
            cat_name = cat.get("category") or cat.get("title") or cat.get("name") or ""
            heading = f"{cat_name} ({cat['subtitle']})" if cat.get("subtitle") else cat_name
            items = []
            for sub in cat.get("subcategory", []):
                items.append({
                    "label": sub,
                    "href": f"product-range.html?category={slugify(sub)}"
                })
            product_columns.append({
                "heading": heading,
                "items": items
            })

        # 6. Define static Company mega menu
        company_mega_menu = {
            "sections": [
                {
                    "heading": "Explore by Organization",
                    "links": [
                        { "label": "Our Services", "href": "services.html" },
                        { "label": "Global Presence", "href": "global-presence.html" },
                        { "label": "Patient Assistance Program", "href": "pap.html", "isLogoLink": True, "logoSrc": "assets/PAPlogo.png", "logoAlt": "Patient Assistance Program" }
                    ]
                },
                {
                    "heading": "More Information",
                    "links": [
                        { "label": "CSR", "href": "csr.html" },
                        { "label": "Careers", "href": "careers.html" },
                        { "label": "United Nations Global Compact", "href": "ungc.html" }
                    ]
                }
            ],
            "slides": [
                {
                    "image": "assets/about_us_hero.png",
                    "title": "About Us",
                    "description": "Learn more about our mission and vision."
                },
                {
                    "image": "assets/globalpresencehero.jpg",
                    "title": "Global Presence",
                    "description": "We are expanding healthcare solutions worldwide."
                },
                {
                    "image": "assets/careershero.png",
                    "title": "Careers",
                    "description": "Join our team and make a difference."
                }
            ]
        }

        # 7. Build dynamic Mobile sublinks
        mobile_product_links = []
        for cat in categories:
            cat_name = cat.get("category") or cat.get("title") or cat.get("name") or ""
            cat_slug = cat.get("slug", {}).get("current") if (cat.get("slug") and isinstance(cat["slug"], dict)) else slugify(cat_name)
            mobile_product_links.append({
                "label": cat_name,
                "href": f"product-range.html?category={cat_slug}"
            })

        return {
            "logo": logo,
            "mainLinks": main_links,
            "productMegaMenu": { "columns": product_columns },
            "companyMegaMenu": company_mega_menu,
            "mobileMenu": {
                "productSubLinks": mobile_product_links,
                "companyLabel": "Company"
            }
        }
    except Exception as e:
        print(f"Error dynamically building navigation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/footer")
async def get_footer():
    """
    Dynamically generates the footer configuration (footer.json)
    by pulling from siteSettings (branding, copyright, legal links, contact, socials).
    """
    try:
        # Fetch global site settings
        settings_query = '*[_type == "siteSettings" && _id == "global-site-settings"][0]'
        settings = await sanity_service.query_sanity(settings_query) or {}

        # Build branding block
        logo_data = settings.get("logo", {})
        branding = {
            "logo": {
                "src": logo_data.get("src", "assets/getmedslogo.png"),
                "alt": logo_data.get("alt", "GetMEDS Logo")
            },
            "description": "GetMEDS is your trusted online healthcare partner, providing access to top-quality medicines, doctor consultations, and lab tests from anywhere in the world."
        }

        # Format socials (clean any Sanity attributes)
        socials = []
        for soc in settings.get("socials", []):
            socials.append({
                "platform": soc.get("platform", ""),
                "icon": soc.get("icon", ""),
                "href": soc.get("href", "#")
            })

        # Format contact info
        contact_info = settings.get("contactInfo", {})
        
        # Build link groups
        link_groups = [
            {
                "heading": "About",
                "links": [
                    { "label": "About Us", "href": "about-us.html" },
                    { "label": "Our Leadership", "href": "#" },
                    { "label": "Careers", "href": "#" },
                    { "label": "News & Media", "href": "#" }
                ]
            },
            {
                "heading": "Delivery",
                "links": [
                    { "label": "Track Order", "href": "#" },
                    { "label": "Return Policy", "href": "#" },
                    { "label": "Delivery Info", "href": "#" },
                    { "label": "FAQs", "href": "#" }
                ]
            },
            {
                "heading": "Contact",
                "items": [
                    { "type": "address", "icon": "fa-solid fa-location-dot", "text": contact_info.get("address", "123 Medical Drive, Health City, NY 10001") },
                    { "type": "phone", "icon": "fa-solid fa-phone", "text": contact_info.get("phone", "+1 (800) 123-4567") },
                    { "type": "email", "icon": "fa-solid fa-envelope", "text": contact_info.get("email", "support@getmeds.com") }
                ]
            }
        ]

        # Format legal links
        legal_links = []
        for link in settings.get("legalLinks", []):
            legal_links.append({
                "label": link.get("label", ""),
                "href": link.get("href", "#")
            })

        return {
            "branding": branding,
            "socials": socials,
            "linkGroups": link_groups,
            "bottomBar": {
                "copyright": settings.get("copyright", "© 2023 GetMEDS. All rights reserved."),
                "legalLinks": legal_links
            }
        }
    except Exception as e:
        print(f"Error dynamically building footer: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/products")
async def get_products():
    """
    Dynamically generates the products config (products.json)
    by combining searchSuggestions from productsPage settings with categories from Sanity category schemas.
    """
    try:
        # 1. Query search suggestions from productsPage settings
        prod_settings_query = '*[_type == "productsPage" && _id == "products-page"][0]'
        prod_settings = await sanity_service.query_sanity(prod_settings_query) or {}

        # 2. Query categories
        categories_query = '*[_type == "category"] | order(category asc)'
        categories = await sanity_service.query_sanity(categories_query) or []

        # 3. Format dynamic categories list
        formatted_categories = []
        for cat in categories:
            cat_name = cat.get("category") or cat.get("title") or cat.get("name") or ""
            cat_slug = cat.get("slug", {}).get("current") if (cat.get("slug") and isinstance(cat["slug"], dict)) else slugify(cat_name)
            subcategories = []
            for sub in cat.get("subcategory", []):
                subcategories.append({
                    "id": slugify(sub),
                    "name": sub
                })
            formatted_categories.append({
                "id": cat_slug,
                "name": f"{cat_name} ({cat['subtitle']})" if cat.get("subtitle") else cat_name,
                "subcategories": subcategories
            })

        return {
            "categories": formatted_categories,
            "searchSuggestions": prod_settings.get("searchSuggestions", [])
        }
    except Exception as e:
        print(f"Error dynamically building products page config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{page_name}")
async def get_page_content(page_name: str):
    """
    Retrieves the content of a page configuration from Sanity.
    """
    if page_name not in PAGE_MAPPINGS:
        raise HTTPException(status_code=404, detail=f"Page '{page_name}' not found in configuration mappings.")
    
    mapping = PAGE_MAPPINGS[page_name]
    doc_type = mapping["type"]
    doc_id = mapping["id"]
    
    query = '*[_type == $doc_type && _id == $doc_id][0]'
    params = {
        "$doc_type": doc_type,
        "$doc_id": doc_id
    }
    
    try:
        doc = await sanity_service.query_sanity(query, params)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document with type '{doc_type}' and ID '{doc_id}' not found in Sanity.")
        
        return clean_sanity_document(doc)
    except Exception as e:
        print(f"Error fetching page content for '{page_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))
