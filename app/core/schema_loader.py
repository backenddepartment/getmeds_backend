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
    "product": { "label": 'Products', "icon": 'fa-pills', "badge": 'bg-blue-50 text-blue-600 border-blue-100/50' },
    "category": { "label": 'Categories', "icon": 'fa-tags', "badge": 'bg-teal-50 text-teal-600 border-teal-100/50' },
    "heroSlide": { "label": 'Hero Slides', "icon": 'fa-images', "badge": 'bg-amber-50 text-amber-600 border-amber-100/50' },
    "service": { "label": 'Services', "icon": 'fa-stethoscope', "badge": 'bg-purple-50 text-purple-600 border-purple-100/50' },
    "dealOfDay": { "label": 'Deals', "icon": 'fa-tag', "badge": 'bg-rose-50 text-rose-600 border-rose-100/50' },
    "categoryBanner": { "label": 'Banners', "icon": 'fa-rectangle-ad', "badge": 'bg-indigo-50 text-indigo-600 border-indigo-100/50' },
    "team": { "label": 'Team Members', "icon": 'fa-user-doctor', "badge": 'bg-emerald-50 text-emerald-600 border-emerald-100/50' },
    "faq": { "label": 'FAQs', "icon": 'fa-circle-question', "badge": 'bg-sky-50 text-sky-600 border-sky-100/50' },
    "chatSession": { "label": 'Chat Sessions', "icon": 'fa-comments', "badge": 'bg-slate-50 text-slate-600 border-slate-100/50' },
}

def get_property_value(prop_name, text):
    pattern = r'\b' + prop_name + r'\s*:\s*(?:\'([^\'\\]*(?:\\.[^\'\\]*)*)\'|"([^"\\]*(?:\\.[^"\\]*)*)"|`([^`\\]*(?:\\.[^`\\]*)*)`|([a-zA-Z0-9_-]+))'
    match = re.search(pattern, text)
    if match:
        val = match.group(1) or match.group(2) or match.group(3) or match.group(4)
        if val == 'true': return True
        if val == 'false': return False
        return val
    return None

def parse_ts_schema(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading schema file {file_path}: {e}")
        return None
    
    # Remove comments
    content = re.sub(r'//.*', '', content)
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    
    doc_name = get_property_value('name', content)
    if not doc_name:
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
                                        bracket_count = 0
                                        nest_start = fields_start_nest.end() - 1
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
                                            nest_fields_block = of_content[nest_start + 1 : nest_end]
                                            n_field_blocks = []
                                            n_brace_count = 0
                                            n_block_start = -1
                                            n_in_string = False
                                            n_string_char = None
                                            n_escaped = False
                                            j = 0
                                            while j < len(nest_fields_block):
                                                char = nest_fields_block[j]
                                                if n_escaped:
                                                    n_escaped = False
                                                    j += 1
                                                    continue
                                                if char == '\\':
                                                    n_escaped = True
                                                    j += 1
                                                    continue
                                                if char in ('\'', '"', '`'):
                                                    if not n_in_string:
                                                        n_in_string = True
                                                        n_string_char = char
                                                    elif n_string_char == char:
                                                        n_in_string = False
                                                elif not n_in_string:
                                                    if char == '{':
                                                        if n_brace_count == 0:
                                                            n_block_start = j
                                                        n_brace_count += 1
                                                    elif char == '}':
                                                        n_brace_count -= 1
                                                        if n_brace_count == 0 and n_block_start != -1:
                                                            n_field_blocks.append(nest_fields_block[n_block_start : j + 1])
                                                            n_block_start = -1
                                                j += 1
                                            
                                            nested_fields_parsed = []
                                            for nfb in n_field_blocks:
                                                nf_name = get_property_value('name', nfb)
                                                nf_title = get_property_value('title', nfb)
                                                nf_type = get_property_value('type', nfb)
                                                nf_desc = get_property_value('description', nfb)
                                                nf_req = 'Rule.required()' in nfb or 'Rule.custom' in nfb
                                                
                                                if nf_name and nf_type:
                                                    nf_data = {
                                                        "name": nf_name,
                                                        "label": nf_title if nf_title else nf_name.capitalize(),
                                                        "type": nf_type,
                                                        "required": nf_req
                                                    }
                                                    if nf_desc:
                                                        nf_data["description"] = nf_desc
                                                        
                                                    # Parse nested initial value
                                                    ninit_m = re.search(r'\binitialValue\s*:\s*(?:\'([^\'\\]*(?:\\.[^\'\\]*)*)\'|"([^"\\]*(?:\\.[^"\\]*)*)"|`([^`\\]*(?:\\.[^`\\]*)*)`|([^,\n\}]+))', nfb)
                                                    if ninit_m:
                                                        nval_str = ninit_m.group(1) or ninit_m.group(2) or ninit_m.group(3) or ninit_m.group(4)
                                                        nval_str = nval_str.strip()
                                                        if nval_str == "true":
                                                            nval = True
                                                        elif nval_str == "false":
                                                            nval = False
                                                        elif re.match(r'^-?\d+$', nval_str):
                                                            nval = int(nval_str)
                                                        elif re.match(r'^-?\d+\.\d+$', nval_str):
                                                            nval = float(nval_str)
                                                        else:
                                                            nval = nval_str
                                                        nf_data["initialValue"] = nval

                                                    # Parse nested hidden condition
                                                    nhidden_m = re.search(r'\bhidden\s*:\s*\(\{\s*parent\s*\}\)\s*=>\s*parent\?\.([a-zA-Z0-9_-]+)\s*(===|==|!==|!=)\s*(true|false|[\'"`][^\'"`]*[\'"`])', nfb)
                                                    if nhidden_m:
                                                        ncond_field = nhidden_m.group(1)
                                                        nop = nhidden_m.group(2)
                                                        nval_str = nhidden_m.group(3)
                                                        nval_str = nval_str.strip('\'"` ')
                                                        if nval_str == "true":
                                                            nval = True
                                                        elif nval_str == "false":
                                                            nval = False
                                                        elif re.match(r'^-?\d+$', nval_str):
                                                            nval = int(nval_str)
                                                        elif re.match(r'^-?\d+\.\d+$', nval_str):
                                                            nval = float(nval_str)
                                                        else:
                                                            nval = nval_str
                                                        nf_data["hidden_condition"] = {
                                                            "field": ncond_field,
                                                            "operator": "eq" if nop in ("===", "==") else "neq",
                                                            "value": nval
                                                        }
                                                    if nf_type == "reference":
                                                        nto_m = re.search(r'\bto\s*:\s*\[\s*\{\s*type\s*:\s*[\'"`]([^\'"`]+)[\'"`]\s*\}\s*\]', nfb)
                                                        if nto_m:
                                                            nf_data["to"] = nto_m.group(1)
                                                    nested_fields_parsed.append(nf_data)
                                            if nested_fields_parsed:
                                                field_data["of_type"] = "object"
                                                field_data["fields"] = nested_fields_parsed
                    
                    fields.append(field_data)
                    
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
                for f in os.listdir(schema_dir):
                    if f.endswith('.ts') and f != 'index.ts':
                        parsed = parse_ts_schema(os.path.join(schema_dir, f))
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
            "heroSlide": "GMH0000-",
            "service": "GMS0000-",
            "dealOfDay": "GMD0000-",
            "categoryBanner": "GMB0000-",
            "team": "GMT0000-",
            "faq": "GMF0000-",
            "chatSession": "GMX0000-",
            "adminUser": "GMAU0000-",
            "securityLog": "GMSL0000-",
            "accessPoint": "GMAP0000-"
        }
        # Add dynamic maps
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
        for s in self.schemas:
            name = s["name"]
            fields_mapped = []
            for f in s["fields"]:
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
                
                # Type mappings
                if ftype == "string":
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
                    # Default boolean options
                    if f["name"] == "availability":
                        mapped_field["options"] = [{"value": "true", "label": "In Stock"}, {"value": "false", "label": "Out of Stock"}]
                    else:
                        mapped_field["options"] = [{"value": "true", "label": "Yes"}, {"value": "false", "label": "No"}]
                elif ftype == "select":
                    mapped_field["type"] = "select"
                    mapped_field["options"] = f.get("options", [])
                elif ftype == "reference":
                    target = f.get("to", "")
                    if name == "product" and f["name"] == "category":
                        mapped_field["type"] = "category_select"
                    else:
                        mapped_field["type"] = "reference_select"
                        mapped_field["to"] = target
                elif name == "product" and f["name"] == "subCategory":
                    mapped_field["type"] = "subcategory_select"
                elif ftype == "array":
                    if f.get("of_type") == "object":
                        mapped_field["type"] = "object_array"
                        # Map nested fields
                        nested_mapped = []
                        for nf in f.get("fields", []):
                            nftype = nf["type"]
                            n_mapped = {
                                "name": nf["name"],
                                "label": nf["label"],
                                "required": nf.get("required", False)
                            }
                            if "description" in nf:
                                n_mapped["description"] = nf["description"]
                            if "initialValue" in nf:
                                n_mapped["initialValue"] = nf["initialValue"]
                            if "hidden_condition" in nf:
                                n_mapped["hidden_condition"] = nf["hidden_condition"]
                            if nftype == "string":
                                n_mapped["type"] = "text"
                            elif nftype == "slug":
                                n_mapped["type"] = "slug"
                                n_mapped["source"] = nf.get("source", "name")
                            elif nftype == "image":
                                n_mapped["type"] = "image"
                            elif nftype == "text":
                                n_mapped["type"] = "textarea"
                            elif nftype == "number":
                                n_mapped["type"] = "number"
                                n_mapped["step"] = "0.01"
                            elif nftype == "boolean":
                                n_mapped["type"] = "select"
                                n_mapped["options"] = [{"value": "true", "label": "Yes"}, {"value": "false", "label": "No"}]
                            elif nftype == "reference":
                                n_mapped["type"] = "reference_select"
                                n_mapped["to"] = nf.get("to", "")
                            else:
                                n_mapped["type"] = "text"
                            nested_mapped.append(n_mapped)
                        mapped_field["fields"] = nested_mapped
                    else:
                        mapped_field["type"] = "text"
                        mapped_field["placeholder"] = "Comma-separated values (e.g. tag1, tag2)"
                        mapped_field["is_array"] = True
                else:
                    mapped_field["type"] = "text"
                
                fields_mapped.append(mapped_field)
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
                meta[name] = {
                    "label": s["title"] + "s" if not s["title"].endswith("s") else s["title"],
                    "icon": "fa-database",
                    "badge": "bg-slate-50 text-slate-600 border-slate-100/50"
                }
        return meta

    def get_image_collections(self):
        img_cols = []
        for s in self.schemas:
            if any(f["type"] == "image" for f in s["fields"]):
                img_cols.append(s["name"])
        return img_cols

schema_loader = SchemaLoader()
