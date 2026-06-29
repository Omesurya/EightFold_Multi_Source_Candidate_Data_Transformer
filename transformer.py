import json
import re
import sys

# ==========================================
# 1. BASE CANONICAL SCHEMA & NORMALIZERS
# ==========================================

def normalize_phone(phone_str):
    if not phone_str:
        return None
    # Strip non-numeric tokens
    digits = re.sub(r'\D', '', str(phone_str))
    if len(digits) == 10:
        return f"+1{digits}" # Default E.164 fallback assumption
    elif len(digits) > 10:
        return f"+{digits}"
    return None

def normalize_date(date_str):
    if not date_str:
        return None
    # Crude fuzzy match for YYYY-MM conversion
    match = re.search(r'(\d{4})[-/](\d{2})', str(date_str))
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    match_year = re.search(r'\b(\d{4})\b', str(date_str))
    if match_year:
        return f"{match_year.group(1)}-01"
    return None

def normalize_skill(skill_name):
    # Standardize skills to lowercase clean variants
    return skill_name.strip().lower() if skill_name else ""

# ==========================================
# 2. SOURCE PARSERS
# ==========================================

def parse_ats_json(json_str, source_name="ats_json"):
    """ Parses structured ATS JSON blobs with custom field naming. """
    try:
        data = json.loads(json_str)
    except Exception:
        return [] # Graceful degradation
        
    candidates = []
    # Assumes data could be a single object or list
    items = data if isinstance(data, list) else [data]
    
    for item in items:
        raw_emails = item.get("email_addresses", [])
        if isinstance(raw_emails, str):
            raw_emails = [raw_emails]
            
        raw_phones = item.get("contact_numbers", [])
        if isinstance(raw_phones, str):
            raw_phones = [raw_phones]

        candidate = {
            "full_name": item.get("legal_name"),
            "emails": [e.strip().lower() for e in raw_emails if e],
            "phones": [normalize_phone(p) for p in raw_phones if normalize_phone(p)],
            "skills": [normalize_skill(s) for s in item.get("tech_stack", [])],
            "source_meta": {"name": source_name, "confidence_weight": 0.95, "method": "json_parser"}
        }
        candidates.append(candidate)
    return candidates

def parse_recruiter_notes(text_content, source_name="recruiter_notes"):
    """ Parses unstructured free-form text using Regex extractions. """
    candidates = []
    # Regex rules to extract parameters out of textual paragraphs
    email_matches = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text_content)
    phone_matches = re.findall(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', text_content)
    
    # Try finding candidate name via "Candidate: Name" keyword format or fall back
    name_match = re.search(r'(?:Candidate|Name):\s*([A-Za-z\s]+)', text_content, re.IGNORECASE)
    full_name = name_match.group(1).strip() if name_match else "Unknown Candidate"
    
    if email_matches or phone_matches:
        candidate = {
            "full_name": full_name,
            "emails": [e.strip().lower() for e in email_matches],
            "phones": [normalize_phone(p) for p in phone_matches if normalize_phone(p)],
            "skills": [], # hard to glean confidently without advanced NLP models
            "source_meta": {"name": source_name, "confidence_weight": 0.50, "method": "regex_extraction"}
        }
        candidates.append(candidate)
    return candidates

# ==========================================
# 3. MERGE / LINKAGE ENGINE
# ==========================================

class CandidateRegistry:
    def __init__(self):
        self.profiles = {}

    def add_candidates(self, candidates):
        for c in candidates:
            # Find an existing profile connection index key
            lookup_key = None
            for email in c["emails"]:
                if email in self.profiles:
                    lookup_key = self.profiles[email]
                    break
            
            if not lookup_key:
                for phone in c["phones"]:
                    if phone in self.profiles:
                        lookup_key = self.profiles[phone]
                        break
                        
            if lookup_key:
                # Merge into existing record
                self._merge_records(lookup_key, c)
            else:
                # Generate new base structural registry record
                new_id = f"CAN_{len(self.profiles) + 1001}"
                new_profile = {
                    "candidate_id": new_id,
                    "full_name": c["full_name"],
                    "emails": list(set(c["emails"])),
                    "phones": list(set(c["phones"])),
                    "skills": list(set(c["skills"])),
                    "provenance": [],
                    "highest_confidence": c["source_meta"]["confidence_weight"]
                }
                
                # Setup mapping paths
                for m in new_profile["emails"]: self.profiles[m] = new_profile
                for p in new_profile["phones"]: self.profiles[p] = new_profile
                
                self._track_provenance(new_profile, c)
                
    def _track_provenance(self, profile, incoming):
        meta = incoming["source_meta"]
        for key in ["full_name", "emails", "phones", "skills"]:
            if incoming.get(key):
                profile["provenance"].append({
                    "field": key,
                    "source": meta["name"],
                    "method": meta["method"]
                })

    def _merge_records(self, existing, incoming):
        incoming_weight = incoming["source_meta"]["confidence_weight"]
        # If incoming source has higher confidence validity override the text descriptors
        if incoming_weight > existing["highest_confidence"]:
            if incoming.get("full_name"):
                existing["full_name"] = incoming["full_name"]
            existing["highest_confidence"] = incoming_weight
            
        # Append lists
        existing["emails"] = list(set(existing["emails"] + incoming["emails"]))
        existing["phones"] = list(set(existing["phones"] + incoming["phones"]))
        existing["skills"] = list(set(existing["skills"] + incoming["skills"]))
        self._track_provenance(existing, incoming)

    def get_canonical_profiles(self):
        # Return unique list objects
        seen_ids = set()
        unique_profiles = []
        for p in self.profiles.values():
            if p["candidate_id"] not in seen_ids:
                seen_ids.add(p["candidate_id"])
                unique_profiles.append(p)
        return unique_profiles

# ==========================================
# 4. CONFIGURABLE PROJECTION LAYER
# ==========================================

def project_profile(canonical, config):
    output = {}
    on_missing = config.get("on_missing", "null")
    include_confidence = config.get("include_confidence", True)
    
    for field_cfg in config.get("fields", []):
        target_path = field_cfg["path"]
        from_path = field_cfg.get("from", target_path)
        required = field_cfg.get("required", False)
        
        # Resolving deep simple paths or indexed arrays (e.g. "emails[0]")
        val = None
        try:
            if "[" in from_path and "]" in from_path:
                base_field, idx_str = from_path.split("[")
                idx = int(idx_str.replace("]", ""))
                val = canonical.get(base_field, [])[idx]
            else:
                val = canonical.get(from_path)
        except (IndexError, KeyError, ValueError):
            val = None

        if val is None or val == []:
            if required and on_missing == "error":
                raise ValueError(f"Required field pathways missing target: {target_path}")
            if on_missing == "omit":
                continue
            else:
                output[target_path] = None
        else:
            output[target_path] = val
            
    if include_confidence:
        output["overall_confidence"] = canonical["highest_confidence"]
        output["provenance"] = canonical["provenance"]
        
    return output

# ==========================================
# 5. CLI PIPELINE INTEGRATION RUNNER
# ==========================================

def main():
    # Sample Test Inputs (Simulating data streams files)
    sample_ats_json = """
    {
        "legal_name": "Jane Doe",
        "email_addresses": ["jane.doe@workmail.com"],
        "contact_numbers": ["555-123-4567"],
        "tech_stack": ["Java", "Python"]
    }
    """
    
    sample_recruiter_notes = """
    Candidate Notes: Spoke with Jane Doe today. 
    Reach out to alternate backup mail jane.doe@workmail.com or call at 5551234567.
    Extremely strong communication skills.
    """

    # Parse and Load Inputs
    registry = CandidateRegistry()
    registry.add_candidates(parse_ats_json(sample_ats_json))
    registry.add_candidates(parse_recruiter_notes(sample_recruiter_notes))
    
    canonical_list = registry.get_canonical_profiles()
    
    # Target Configuration Scheme (Matching Screenshot 2026-06-29 214505.png structural model)
    runtime_config = {
        "fields": [
            { "path": "full_name", "type": "string", "required": True },
            { "path": "primary_email", "from": "emails[0]", "type": "string", "required": True },
            { "path": "phone", "from": "phones[0]", "type": "string" },
            { "path": "skills", "type": "array" }
        ],
        "include_confidence": True,
        "on_missing": "null"
    }

    print("--- EMITTING PROJECTED RUNTIME SCHEMAS ---")
    for profile in canonical_list:
        projected = project_profile(profile, runtime_config)
        print(json.dumps(projected, indent=2))

if __name__ == "__main__":
    main()