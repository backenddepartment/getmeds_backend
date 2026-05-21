import os
import re
import json
import time
from app.core.config import get_settings

settings = get_settings()

SYSTEM_SCHEMAS = {
    "adminUser": [
        { "name": 'username', "label": 'Username', "type": 'text', "required": True, "placeholder": 'e.g. jessica' },
        { "name": 'role', "label": 'Role', "type": 'role_select', "required": True, "placeholder": 'e.g. Administrator' },
        { "name": 'permissions', "label": 'Permissions (comma separated)', "type": 'text', "required": True, "placeholder": 'e.g. CMS Mutations, Logs' },
        { "name": 'status', "label": 'Status', "type": 'select', "options": [{ "value": 'Active', "label": 'Active' }, { "value": 'Suspended', "label": 'Suspended' }] },
        { "name": 'passcode', "label": 'Passcode', "type": 'text', "required": True, "placeholder": 'e.g. GMP-JESSICA-2026' }
    ],
    "accessPoint": [
        { "name": 'resource', "label": 'Resource / Path', "type": 'text', "required": True, "placeholder": 'e.g. /api/admin/security/users' },
        { "name": 'allowed_roles', "label": 'Allowed Roles', "type": 'text', "required": True, "placeholder": 'e.g. Administrator, Security Officer' },
        { "name": 'auth_type', "label": 'Auth Type', "type": 'text', "required": True, "placeholder": 'e.g. Master Secret or Operator Session' }
    ]
}

COLLECTION_META_DEFAULTS = {
    # ── Core Data (table/list view) ──
    "product":    { "label": "Products",      "icon": "fa-pills",            "badge": "bg-blue-50 text-blue-600 border-blue-100/50",    "group": "core",     "viewType": "table" },
    "category":   { "label": "Categories",    "icon": "fa-tags",             "badge": "bg-teal-50 text-teal-600 border-teal-100/50",    "group": "core",     "viewType": "table" },
    "faq":        { "label": "FAQs",          "icon": "fa-circle-question",  "badge": "bg-sky-50 text-sky-600 border-sky-100/50",      "group": "core",     "viewType": "table" },
    "chatSession":{ "label": "Chat Sessions", "icon": "fa-comments",         "badge": "bg-slate-50 text-slate-600 border-slate-100/50", "group": "core",     "viewType": "table" },

    # ── Pages (singleton form editor) ──
    "homePage":           { "label": "Home",                      "icon": "fa-house",          "badge": "bg-violet-50 text-violet-600 border-violet-100/50",  "group": "pages", "viewType": "singleton", "singletonId": "home-page" },
    "aboutPage":          { "label": "About Us",                  "icon": "fa-building",       "badge": "bg-violet-50 text-violet-600 border-violet-100/50",  "group": "pages", "viewType": "singleton", "singletonId": "about-page" },
    "servicesPage":       { "label": "Services",                  "icon": "fa-stethoscope",    "badge": "bg-violet-50 text-violet-600 border-violet-100/50",  "group": "pages", "viewType": "singleton", "singletonId": "services-page" },
    "contactPage":        { "label": "Contact",                   "icon": "fa-envelope",       "badge": "bg-violet-50 text-violet-600 border-violet-100/50",  "group": "pages", "viewType": "singleton", "singletonId": "contact-page" },
    "careersPage":        { "label": "Careers",                   "icon": "fa-briefcase",      "badge": "bg-violet-50 text-violet-600 border-violet-100/50",  "group": "pages", "viewType": "singleton", "singletonId": "careers-page" },
    "meditationsPage":    { "label": "Meditations",               "icon": "fa-spa",            "badge": "bg-violet-50 text-violet-600 border-violet-100/50",  "group": "pages", "viewType": "singleton", "singletonId": "meditations-page" },
    "orderMedicinesPage": { "label": "Order Medicines",           "icon": "fa-cart-shopping",  "badge": "bg-violet-50 text-violet-600 border-violet-100/50",  "group": "pages", "viewType": "singleton", "singletonId": "order-medicines-page" },
    "productsPage":       { "label": "Product Range",             "icon": "fa-boxes-stacked",  "badge": "bg-violet-50 text-violet-600 border-violet-100/50",  "group": "pages", "viewType": "singleton", "singletonId": "products-page" },
    "globalPresencePage": { "label": "Global Presence",           "icon": "fa-globe",          "badge": "bg-violet-50 text-violet-600 border-violet-100/50",  "group": "pages", "viewType": "singleton", "singletonId": "global-presence-page" },
    "csrPage":            { "label": "CSR",                       "icon": "fa-hand-holding-heart", "badge": "bg-violet-50 text-violet-600 border-violet-100/50", "group": "pages", "viewType": "singleton", "singletonId": "csr-page" },
    "ungcPage":           { "label": "UNGC",                      "icon": "fa-flag",           "badge": "bg-violet-50 text-violet-600 border-violet-100/50",  "group": "pages", "viewType": "singleton", "singletonId": "ungc-page" },
    "papPage":            { "label": "Patient Assistance Program","icon": "fa-hand-holding-medical", "badge": "bg-violet-50 text-violet-600 border-violet-100/50", "group": "pages", "viewType": "singleton", "singletonId": "pap-page" },

    # ── Settings (singleton form editor) ──
    "siteSettings":       { "label": "Site Settings",             "icon": "fa-gear",           "badge": "bg-amber-50 text-amber-600 border-amber-100/50",    "group": "settings", "viewType": "singleton", "singletonId": "global-site-settings" },
}

# Sidebar group definitions (order matters for rendering)
SIDEBAR_GROUPS = [
    { "key": "core",     "label": "Core Data", "icon": "fa-database" },
    { "key": "pages",    "label": "Pages",     "icon": "fa-file-lines" },
    { "key": "settings", "label": "Settings",  "icon": "fa-gear" },
]

def get_property_value(prop_name, text):
    pattern = r'\b' + prop_name + r'\s*:\s*(?:\'([^\'\\]*(?:\\.[^\'\\]*)*)\'|"([^"\\]*(?:\\.[^"\\]*)*)"|`([^`\\]*(?:\\.[^`\\]*)*)`|([a-zA-Z0-9_-]+))'
    match = re.search(pattern, text)
    if match:
        val = match.group(1) or match.group(2) or match.group(3) or match.group(4)
        if val == 'true': return True
        if val == 'false': return False
        return val
    return None

def parse_fields_from_block(fields_block):
    field_blocks = []
    brace_count = 0
    block_start = -1
    in_string = False
    string_char = None
    escaped = False
    
    i = 0
    while i < len(fields_block):
        char = fields_block[i]
        if escaped:
            escaped = False
            i += 1
            continue
        if char == '\\':
            escaped = True
            i += 1
            continue
        if char in ('\'', '"', '`'):
            if not in_string:
                in_string = True
                string_char = char
            elif string_char == char:
                in_string = False
        elif not in_string:
            if char == '{':
                if brace_count == 0:
                    block_start = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and block_start != -1:
                    field_blocks.append(fields_block[block_start : i + 1])
                    block_start = -1
        i += 1
    
    fields = []
    for fb in field_blocks:
        f_name = get_property_value('name', fb)
        f_title = get_property_value('title', fb)
        f_type = get_property_value('type', fb)
        f_desc = get_property_value('description', fb)
        
        is_req = False
        if 'Rule.required()' in fb or 'Rule.custom' in fb:
            is_req = True
        
        if f_name and f_type:
            field_data = {
                "name": f_name,
                "label": f_title if f_title else f_name.capitalize(),
                "type": f_type,
                "required": is_req
            }
            if f_desc:
                field_data["description"] = f_desc
                
            # Parse initial value
            init_m = re.search(r'\binitialValue\s*:\s*(?:\'([^\'\\]*(?:\\.[^\'\\]*)*)\'|"([^"\\]*(?:\\.[^"\\]*)*)"|`([^`\\]*(?:\\.[^`\\]*)*)`|([^,\n\}]+))', fb)
            if init_m:
                val_str = init_m.group(1) or init_m.group(2) or init_m.group(3) or init_m.group(4)
                val_str = val_str.strip()
                if val_str == "true":
                    val = True
                elif val_str == "false":
                    val = False
                elif re.match(r'^-?\d+$', val_str):
                    val = int(val_str)
                elif re.match(r'^-?\d+\.\d+$', val_str):
                    val = float(val_str)
                else:
                    val = val_str
                field_data["initialValue"] = val

            # Parse hidden condition
            hidden_m = re.search(r'\bhidden\s*:\s*\(\{\s*parent\s*\}\)\s*=>\s*parent\?\.([a-zA-Z0-9_-]+)\s*(===|==|!==|!=)\s*(true|false|[\'"`][^\'"`]*[\'"`])', fb)
            if hidden_m:
                cond_field = hidden_m.group(1)
                op = hidden_m.group(2)
                val_str = hidden_m.group(3)
                val_str = val_str.strip('\'"` ')
                if val_str == "true":
                    val = True
                elif val_str == "false":
                    val = False
                elif re.match(r'^-?\d+$', val_str):
                    val = int(val_str)
                elif re.match(r'^-?\d+\.\d+$', val_str):
                    val = float(val_str)
                else:
                    val = val_str
                field_data["hidden_condition"] = {
                    "field": cond_field,
                    "operator": "eq" if op in ("===", "==") else "neq",
                    "value": val
                }
                
            if "options" in fb:
                list_m = re.search(r'\blist\s*:\s*\[(.*?)\]', fb, flags=re.DOTALL)
                if list_m:
                    opts = []
                    opt_items = re.findall(r'\{\s*title\s*:\s*(?:\'([^\'\\]*(?:\\.[^\'\\]*)*)\'|"([^"\\]*(?:\\.[^"\\]*)*)"|`([^`\\]*(?:\\.[^`\\]*)*)`)\s*,\s*value\s*:\s*(?:\'([^\'\\]*(?:\\.[^\'\\]*)*)\'|"([^"\\]*(?:\\.[^"\\]*)*)"|`([^`\\]*(?:\\.[^`\\]*)*)`)\s*\}', list_m.group(1))
                    for match_groups in opt_items:
                        title = match_groups[0] or match_groups[1] or match_groups[2]
                        value = match_groups[3] or match_groups[4] or match_groups[5]
                        opts.append({"value": value, "label": title})
                    if opts:
                        field_data["type"] = "select"
                        field_data["options"] = opts
            
            if field_data["type"] == "reference":
                to_m = re.search(r'\bto\s*:\s*\[\s*\{\s*type\s*:\s*[\'"`]([^\'"`]+)[\'"`]\s*\}\s*\]', fb)
                if to_m:
                    field_data["to"] = to_m.group(1)
            
            if field_data["type"] == "slug":
                source_m = re.search(r'\bsource\s*:\s*[\'"`]([^\'"`]+)[\'"`]', fb)
                if source_m:
                    field_data["source"] = source_m.group(1)
                    
            if field_data["type"] == "object":
                fields_start_nest = re.search(r'\bfields\s*:\s*\[', fb)
                if fields_start_nest:
                    bracket_count = 1
                    nest_start = fields_start_nest.end()
                    nest_end = -1
                    for idx in range(nest_start, len(fb)):
                        char = fb[idx]
                        if char == '[':
                            bracket_count += 1
                        elif char == ']':
                            bracket_count -= 1
                            if bracket_count == 0:
                                nest_end = idx
                                break
                    if nest_end != -1:
                        nest_fields_block = fb[nest_start : nest_end]
                        nested_fields_parsed = parse_fields_from_block(nest_fields_block)
                        if nested_fields_parsed:
                            field_data["of_type"] = "object"
                            field_data["fields"] = nested_fields_parsed

            if field_data["type"] == "array":
                of_start = re.search(r'\bof\s*:\s*\[', fb)
                if of_start:
                    bracket_count = 1
                    nest_start = of_start.end()
                    nest_end = -1
                    for idx in range(nest_start, len(fb)):
                        char = fb[idx]
                        if char == '[':
                            bracket_count += 1
                        elif char == ']':
                            bracket_count -= 1
                            if bracket_count == 0:
                                nest_end = idx
                                break
                    if nest_end != -1:
                        of_content = fb[nest_start : nest_end]
                        if 'fields' in of_content:
                            fields_start_nest = re.search(r'\bfields\s*:\s*\[', of_content)
                            if fields_start_nest:
                                bracket_count = 1
                                nest_start = fields_start_nest.end()
                                nest_end = -1
                                for idx in range(nest_start, len(of_content)):
                                    char = of_content[idx]
                                    if char == '[':
                                        bracket_count += 1
                                    elif char == ']':
                                        bracket_count -= 1
                                        if bracket_count == 0:
                                            nest_end = idx
                                            break
                                if nest_end != -1:
                                    nest_fields_block = of_content[nest_start : nest_end]
                                    nested_fields_parsed = parse_fields_from_block(nest_fields_block)
                                    if nested_fields_parsed:
                                        field_data["of_type"] = "object"
                                        field_data["fields"] = nested_fields_parsed
                        else:
                            type_m = re.search(r'type\s*:\s*[\'"`]([^\'"`]+)[\'"`]', of_content)
                            if type_m:
                                of_type_name = type_m.group(1)
                                if of_type_name in ("imageWithAlt", "metaFields", "linkItem"):
                                    field_data["of_type"] = of_type_name
            fields.append(field_data)
    return fields

def parse_ts_schema(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading schema file {file_path}: {e}")
        return None
    
    content = re.sub(r'//.*', '', content)
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    
    doc_name = get_property_value('name', content)
    if not doc_name:
        return None
    
    doc_type = get_property_value('type', content)
    if doc_type and doc_type != 'document':
        return None
        
    doc_title = get_property_value('title', content) or doc_name.capitalize()
    
    fields_start = re.search(r'\bfields\s*:\s*\[', content)
    fields = []
    if fields_start:
        start_idx = fields_start.end() - 1
        bracket_count = 0
        end_idx = -1
        for i in range(start_idx, len(content)):
            char = content[i]
            if char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
                if bracket_count == 0:
                    end_idx = i
                    break
        if end_idx != -1:
            fields_block = content[start_idx + 1 : end_idx]
            fields = parse_fields_from_block(fields_block)
            
    return {
        "name": doc_name,
        "title": doc_title,
        "fields": fields
    }

class SchemaLoader:
    def __init__(self):
        self.cached_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cached_schemas.json")
        self.schemas = []
        self.last_load_time = 0.0
        self.load()

    def load(self, force=False):
        now = time.time()
        if not force and now - self.last_load_time < 2.0:
            return
        self.last_load_time = now
        # Determine schema directory path (peer directory relative to app)
        schema_dir = os.environ.get("SANITY_SCHEMA_DIR")
        if not schema_dir:
            # Sibling of getmeds_backend (getmeds_backend/app/core/schema_loader.py -> ../../../getmeds_database/schema)
            schema_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "getmeds_database", "schema"))

        parsed_list = []
        if os.path.exists(schema_dir) and os.path.isdir(schema_dir):
            try:
                for root, dirs, files in os.walk(schema_dir):
                    for f in files:
                        if f.endswith('.ts') and f != 'index.ts':
                            parsed = parse_ts_schema(os.path.join(root, f))
                            if parsed:
                                parsed_list.append(parsed)
            except Exception as e:
                print(f"WARNING: Dynamic schema parsing failed: {e}. Falling back to cache.")

        if parsed_list:
            self.schemas = parsed_list
            # Update cache file
            try:
                with open(self.cached_file, 'w', encoding='utf-8') as f:
                    json.dump(parsed_list, f, indent=2)
            except Exception as e:
                print(f"WARNING: Could not update schemas cache: {e}")
        else:
            # Fallback to cache
            if os.path.exists(self.cached_file):
                try:
                    with open(self.cached_file, 'r', encoding='utf-8') as f:
                        self.schemas = json.load(f)
                    print("Loaded schemas from cache file.")
                except Exception as e:
                    print(f"ERROR: Could not load schemas from cache: {e}")
            else:
                print("WARNING: No schema cache found!")

    def get_schemas(self):
        return self.schemas

    def get_supported_types(self):
        return [s["name"] for s in self.schemas]

    def get_prefix_map(self):
        base_map = {
            "product": "GMP0000-",
            "category": "GMC0000-",
            "faq": "GMF0000-",
            "chatSession": "GMX0000-",
            "siteSettings": "GMSS0000-",
            "adminUser": "GMAU0000-",
            "securityLog": "GMSL0000-",
            "accessPoint": "GMAP0000-"
        }
        # Add dynamic maps for any new schemas
        for s in self.schemas:
            name = s["name"]
            if name not in base_map:
                base_map[name] = f"GM{name[:2].upper()}0000-"
        return base_map

    def get_groq_projections(self):
        projections = {}
        for s in self.schemas:
            name = s["name"]
            field_names = [f["name"] for f in s["fields"]]
            # Include basic Sanity metadata fields
            all_fields = ["_id", "_type", "_createdAt"] + field_names
            projections[name] = "{" + ", ".join(all_fields) + "}"
        return projections

    def get_field_schemas(self):
        fs = {}
        
        # Predefined expansions for shared object types
        SHARED_EXPANSIONS = {
            "metaFields": [
                {"name": "title", "label": "Meta Title", "type": "text"},
                {"name": "description", "label": "Meta Description", "type": "textarea"}
            ],
            "imageWithAlt": [
                {"name": "src", "label": "Image Path", "type": "image_path"},
                {"name": "alt", "label": "Alt Text", "type": "text"}
            ],
            "linkItem": [
                {"name": "label", "label": "Label", "type": "text"},
                {"name": "href", "label": "URL", "type": "text"}
            ]
        }
        
        def map_field_definition(f, parent_name):
            ftype = f["type"]
            mapped_field = {
                "name": f["name"],
                "label": f["label"],
                "required": f.get("required", False)
            }
            if "description" in f:
                mapped_field["description"] = f["description"]
            if "initialValue" in f:
                mapped_field["initialValue"] = f["initialValue"]
            if "hidden_condition" in f:
                mapped_field["hidden_condition"] = f["hidden_condition"]
            
            # 1. Custom Shared Types
            if ftype in SHARED_EXPANSIONS:
                mapped_field["type"] = "object"
                mapped_field["schemaType"] = ftype
                mapped_field["fields"] = SHARED_EXPANSIONS[ftype]
                
            # 2. Object Type
            elif ftype == "object":
                mapped_field["type"] = "object"
                mapped_field["schemaType"] = "object"
                nested_mapped = []
                for nf in f.get("fields", []):
                    nested_mapped.append(map_field_definition(nf, parent_name))
                mapped_field["fields"] = nested_mapped
                
            # 3. Simple Types
            elif ftype == "string":
                name_lower = f["name"].lower()
                if f["name"] == "icon" or f["name"].endswith("Icon"):
                    mapped_field["type"] = "icon_select"
                elif any(kw in name_lower for kw in ("image", "logo", "banner", "pic", "photo", "avatar", "bg")) or f["name"].endswith("Src") or f["name"] == "src":
                    if "alt" not in name_lower:
                        mapped_field["type"] = "image_path"
                    else:
                        mapped_field["type"] = "text"
                else:
                    mapped_field["type"] = "text"
            elif ftype == "slug":
                mapped_field["type"] = "slug"
                mapped_field["source"] = f.get("source", "name")
            elif ftype == "image":
                mapped_field["type"] = "image"
            elif ftype == "text":
                mapped_field["type"] = "textarea"
            elif ftype == "number":
                mapped_field["type"] = "number"
                mapped_field["step"] = "0.01"
            elif ftype == "boolean":
                mapped_field["type"] = "select"
                if f["name"] == "availability":
                    mapped_field["options"] = [{"value": "true", "label": "In Stock"}, {"value": "false", "label": "Out of Stock"}]
                else:
                    mapped_field["options"] = [{"value": "true", "label": "Yes"}, {"value": "false", "label": "No"}]
            elif ftype == "select":
                mapped_field["type"] = "select"
                mapped_field["options"] = f.get("options", [])
            elif ftype == "reference":
                target = f.get("to", "")
                if parent_name == "product" and f["name"] == "category":
                    mapped_field["type"] = "category_select"
                else:
                    mapped_field["type"] = "reference_select"
                    mapped_field["to"] = target
            elif parent_name == "product" and f["name"] == "subCategory":
                mapped_field["type"] = "subcategory_select"
                
            # 4. Array Type
            elif ftype == "array":
                of_type = f.get("of_type")
                if of_type == "object":
                    mapped_field["type"] = "object_array"
                    mapped_field["schemaType"] = "object"
                    nested_mapped = []
                    for nf in f.get("fields", []):
                        nested_mapped.append(map_field_definition(nf, parent_name))
                    mapped_field["fields"] = nested_mapped
                elif of_type in SHARED_EXPANSIONS:
                    mapped_field["type"] = "object_array"
                    mapped_field["schemaType"] = of_type
                    mapped_field["fields"] = SHARED_EXPANSIONS[of_type]
                else:
                    mapped_field["type"] = "chip_array"
                    mapped_field["placeholder"] = "Press Enter to add tag/chip"
                    mapped_field["is_array"] = True
            else:
                mapped_field["type"] = "text"
                
            return mapped_field
            
        for s in self.schemas:
            name = s["name"]
            fields_mapped = []
            for f in s["fields"]:
                fields_mapped.append(map_field_definition(f, name))
            fs[name] = fields_mapped

        # Append system security schemas
        for sys_name, sys_fields in SYSTEM_SCHEMAS.items():
            fs[sys_name] = sys_fields
        return fs

    def get_table_schemas(self):
        ts = {}
        for s in self.schemas:
            name = s["name"]
            cols = []
            
            # Find main field
            main_field = None
            for fname in ("name", "title", "question", "sessionId"):
                if any(f["name"] == fname for f in s["fields"]):
                    main_field = fname
                    break
            
            if not main_field:
                # Fallback to first string/text field
                for f in s["fields"]:
                    if f["type"] in ("string", "text"):
                        main_field = f["name"]
                        break
            
            if not main_field and s["fields"]:
                main_field = s["fields"][0]["name"]
                
            if main_field:
                field_obj = next(f for f in s["fields"] if f["name"] == main_field)
                cols.append({ "key": main_field, "label": field_obj["label"] })
            
            # Select up to 4 other simple fields
            other_fields_added = 0
            for f in s["fields"]:
                if f["name"] == main_field or f["name"] == "slug" or f["type"] == "image":
                    continue
                if name == "chatSession" and f["name"] in ("sessionSummary", "messages"):
                    continue
                if other_fields_added >= 4:
                    break
                
                col_cfg = { "key": f["name"], "label": f["label"] }
                
                # Check formatting type
                if f["type"] == "boolean":
                    col_cfg["type"] = "availability"
                elif f["type"] == "number" and ("price" in f["name"].lower() or "override" in f["name"].lower()):
                    col_cfg["type"] = "price"
                elif f["type"] == "array":
                    col_cfg["type"] = "keywords"
                elif f["type"] == "text":
                    col_cfg["truncate"] = True
                
                cols.append(col_cfg)
                other_fields_added += 1
                
            ts[name] = cols
        return ts

    def get_import_field_schemas(self):
        ifs = {}
        for s in self.schemas:
            # Exclude internal metadata and image fields (which are uploaded separately)
            ifs[s["name"]] = [f["name"] for f in s["fields"] if f["type"] not in ("image", "slug")]
        return ifs

    def get_collection_meta(self):
        meta = COLLECTION_META_DEFAULTS.copy()
        # Add dynamic collections not in default map
        for s in self.schemas:
            name = s["name"]
            if name not in meta:
                # Auto-detect: page schemas go to "pages" group as singletons
                is_page = name.endswith("Page")
                meta[name] = {
                    "label": s["title"],
                    "icon": "fa-file-lines" if is_page else "fa-database",
                    "badge": "bg-violet-50 text-violet-600 border-violet-100/50" if is_page else "bg-slate-50 text-slate-600 border-slate-100/50",
                    "group": "pages" if is_page else "core",
                    "viewType": "singleton" if is_page else "table",
                }
                if is_page:
                    # Derive singletonId from schema name: e.g. "homePage" -> "home-page"
                    import re
                    slug = re.sub(r'([A-Z])', r'-\1', name).lower().lstrip('-')
                    meta[name]["singletonId"] = slug
        return meta

    def get_sidebar_config(self):
        """
        Returns the complete sidebar hierarchy for the admin frontend.
        Groups collections into Core Data / Pages / Settings with viewType metadata.
        """
        meta = self.get_collection_meta()
        
        sidebar = []
        for group_def in SIDEBAR_GROUPS:
            group_key = group_def["key"]
            items = []
            for col_name, col_meta in meta.items():
                if col_meta.get("group") == group_key:
                    item = {
                        "key": col_name,
                        "label": col_meta["label"],
                        "icon": col_meta["icon"],
                        "badge": col_meta["badge"],
                        "viewType": col_meta.get("viewType", "table"),
                    }
                    if col_meta.get("singletonId"):
                        item["singletonId"] = col_meta["singletonId"]
                    items.append(item)
            
            sidebar.append({
                "key": group_key,
                "label": group_def["label"],
                "icon": group_def["icon"],
                "items": items,
            })
        
        return sidebar

    def get_image_collections(self):
        img_cols = []
        for s in self.schemas:
            if any(f["type"] == "image" for f in s["fields"]):
                img_cols.append(s["name"])
        return img_cols

schema_loader = SchemaLoader()

