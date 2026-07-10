"""
Allow-listed GROQ queries executed on behalf of the public frontend.

Why this exists: the frontend used to call Sanity's public data API directly
from the browser (`https://<project>.api.sanity.io/...`), which exposed the
project ID, dataset name, and every raw GROQ query shape to anyone opening
devtools or running curl. That let someone replicate the queries and pull the
entire structured dataset (products, pricing, CMS content) without touching
the rendered site at all.

Moving the query text here means the browser only ever sends a short query
*name* (see app/api/routes/sanity.py) — never the Sanity project ID, dataset,
or GROQ text. `name` must match a key in SANITY_QUERIES, so arbitrary
client-supplied GROQ can never be executed through this endpoint.

Each entry mirrors a query that used to live in
getmeds-frontend/src/lib/queries.ts (or a component that called `client.fetch`
directly) — kept byte-for-byte identical so behavior doesn't change, only the
network path does.
"""

SANITY_QUERIES: dict[str, dict] = {
    "siteSettings.global": {
        "query": """
    *[_type == "siteSettings" && _id == "global-site-settings"][0] {
      ...,
      mainNavigation->
    }
  """
    },
    "navigation.main": {
        "query": """
    *[_type == "navigation" && _id == "main-navigation"][0]
  """
    },
    "product.excelJson": {
        "query": """
    *[_type == "product" && (remarks == "present" || remarks == "active") && defined(title)] | order(_updatedAt desc)[0] {
      json_data
    }
  """
    },
    "product.individualDocs": {
        "query": """
      *[_type == "product" && !defined(title) && (!defined(remarks) || remarks == "present" || remarks == "active")] {
        _id,
        slug,
        image,
        category-> { _id, category, slug },
        subCategory,
        availability,
        genericName,
        brandName,
        name,
        remarks,
        description,
        packaging,
        innovator,
        strength,
        form,
        indications,
        dosageAdministration,
        storageCondition,
        accreditations
      }
    """
    },
    "category.all": {
        "query": """
    *[_type == "category"] | order(category asc) {
      _id,
      category,
      slug,
      subtitle,
      description,
      icon,
      image,
      subcategory,
      categoryId,
    }
  """
    },
    "category.bySlug": {
        "query": """
    *[_type == "category" && slug.current == $slug][0]
  """
    },
    "faq.all": {
        "query": """
    *[_type == "faq"] | order(_createdAt asc)
  """
    },
    "faq.search": {
        "query": """
    *[_type == "faq" && (
      question match $query ||
      answer match $query ||
      $query in keywords
    )]
  """
    },
    "service.all": {
        "query": """
    *[_type == "service"] | order(_createdAt asc)
  """
    },
    "teams.all": {
        "query": """
    *[_type == "teams"] | order(orderRank asc) {
      _id,
      name,
      designation,
      image
    }
  """
    },
    "testimonial.all": {
        "query": """
    *[_type == "testimonial"] | order(rating desc)
  """
    },
    "countryPresence.all": {
        "query": """
    *[_type == "countryPresence"] | order(name asc)
  """
    },
    "csrProgram.all": {
        "query": """
    *[_type == "csrProgram"] | order(_createdAt asc)
  """
    },
    "homePage.main": {
        "query": """
    *[_type == "homePage" && _id == "home-page"][0] {
      ...,
      hero {
        ...,
        slides[0..4] {
          _key,
          heading,
          description,
          enabled,
          image { ..., asset-> }
        }
      }
    }
  """
    },
    "aboutPage.main": {
        "query": """
    *[_type == "aboutPage" && _id == "about-page"][0] {
      ...,
      team {
        ...,
        members[]->
      }
    }
  """
    },
    "careersPage.main": {
        "query": """
    *[_type == "careersPage" && _id == "careers-page"][0]
  """
    },
    "contactPage.main": {
        "query": """
    *[_type == "contactPage" && _id == "contact-page"][0]
  """
    },
    "csrPage.main": {
        "query": """
    *[_type == "csrPage" && _id == "csr-page"][0] {
      ...,
      programs[]->
    }
  """
    },
    "globalPresencePage.main": {
        "query": """
    *[_type == "globalPresencePage" && _id == "global-presence-page"][0] {
      ...,
      countries[]->
    }
  """
    },
    "meditationsPage.main": {
        "query": """
    *[_type == "meditationsPage" && _id == "meditations-page"][0]
  """
    },
    "orderMedicinesPage.main": {
        "query": """
    *[_type == "orderMedicinesPage" && _id == "order-medicines-page"][0]
  """
    },
    "papPage.main": {
        "query": """
    *[_type == "papPage" && _id == "pap-page"][0]
  """
    },
    "productsPage.main": {
        "query": """
    *[_type == "productsPage" && _id == "products-page"][0]
  """
    },
    "servicesPage.main": {
        "query": """
    *[_type == "servicesPage" && _id == "services-page"][0] {
      ...,
      services[]->
    }
  """
    },
    "ungcPage.main": {
        "query": """
    *[_type == "ungcPage" && _id == "ungc-page"][0]
  """
    },
    "pageAsset.all": {
        "query": """
    *[_type == "pageAsset"] | order(name asc) {
      _id,
      _type,
      name,
      images[] {
        image,
        altText,
        enableLink,
        link
      }
    }
  """
    },
    "pageAsset.heroSlides": {
        "query": """
    *[_type == "pageAsset" && name == "Home Hero Background"][0] {
      _id,
      name,
      images[] {
        image { ..., asset-> },
        altText,
        enableLink,
        link
      }
    }
  """
    },
    "pageAsset.byPaths": {
        "query": """*[_type == "pageAsset" && assetPath in $paths] { assetPath, image, page, name }""",
        "array_params": ["paths"],
    },
    "page.heroBundle": {
        "query": """{
      "about":         *[_type == "aboutPage"         && _id == "about-page"][0]          { hero },
      "services":      *[_type == "servicesPage"      && _id == "services-page"][0]       { hero },
      "globalPresence":*[_type == "globalPresencePage"&& _id == "global-presence-page"][0]{ hero },
      "csr":           *[_type == "csrPage"           && _id == "csr-page"][0]            { hero },
      "careers":       *[_type == "careersPage"       && _id == "careers-page"][0]        { hero },
      "ungc":          *[_type == "ungcPage"          && _id == "ungc-page"][0]           { hero }
    }"""
    },
    "googleSpreadsheet.bySlug": {
        "query": """
    *[_type == "googleSpreadsheet" && id.current == $slug][0] {
      _id,
      spreadsheetId,
      link
    }
  """
    },
    "career.all": {
        "query": """
    *[_type == "career"] | order(title asc) {
      _id,
      title,
      "desc": description,
      "responsibilities": keyResponsibilities,
      "requirements": qualificationRequirements,
      image
    }
  """
    },
    "imageAsset.all": {
        "query": """*[_type == "sanity.imageAsset"]{ _id, originalFilename }"""
    },
}
