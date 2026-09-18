
import os
import re
import sqlparse
import requests

# ✅ HuggingFace Inference API (no model loaded in RAM — free tier compatible!)
HF_API_URL = "https://api-inference.huggingface.co/models/mrm8488/t5-base-finetuned-wikiSQL"
HF_API_TOKEN = os.environ.get("HF_API_TOKEN", "")  # Optional: set for faster/priority access

def hf_generate(input_text):
    """Call HuggingFace Inference API to generate SQL from natural language."""
    headers = {}
    if HF_API_TOKEN:
        headers["Authorization"] = f"Bearer {HF_API_TOKEN}"

    payload = {
        "inputs": input_text,
        "parameters": {
            "max_new_tokens": 256,
            "num_beams": 5,
        },
        "options": {
            "wait_for_model": True  # wait if model is cold-starting
        }
    }

    response = requests.post(HF_API_URL, headers=headers, json=payload, timeout=60)

    if response.status_code != 200:
        raise RuntimeError(f"HuggingFace API error {response.status_code}: {response.text}")

    result = response.json()

    # The API returns a list of dicts with 'generated_text'
    if isinstance(result, list) and len(result) > 0:
        return result[0].get("generated_text", "")
    elif isinstance(result, dict) and "generated_text" in result:
        return result["generated_text"]
    else:
        raise RuntimeError(f"Unexpected API response format: {result}")


# ✅ Parse schema string into dictionary
def parse_schema(schema_str):
    schema = {}
    try:
        tables = re.findall(r'(\w+)\(([^)]+)\)', schema_str)
        for table, columns in tables:
            schema[table.lower()] = [col.strip().lower() for col in columns.split(',')]
    except Exception as e:
        print(f"Schema parsing error: {str(e)}")
    return schema

# ✅ Match tokens from NL to schema terms
def map_to_schema(term, schema):
    term_lower = term.lower()
    for table, columns in schema.items():
        if term_lower == table:
            return table
        for col in columns:
            if term_lower == col:
                return f"{table}.{col}"
    return term

# ✅ Validate SQL safely
def is_valid_select(sql):
    try:
        parsed = sqlparse.parse(sql)
        if not parsed:
            return False, "Empty query generated"
        for stmt in parsed:
            if stmt.get_type() != "SELECT":
                return False, "Only SELECT queries are supported"
            for token in stmt.flatten():
                token_value = token.value.upper()
                if token_value in ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE"]:
                    return False, f"Unsupported operation: {token_value}"
                if token_value in [";", "--", "/*"]:
                    return False, "Potential SQL injection detected"
        return True, ""
    except Exception as e:
        return False, f"SQL validation error: {str(e)}"

# ✅ Main cleaning logic with lowercasing for MySQL
def clean_sql(sql, user_input, schema_info=None):
    try:
        sql = re.sub(r'[`";]', '', sql).strip()

        if schema_info:
            for term in re.findall(r'\b\w+\b', user_input):
                mapped = map_to_schema(term, schema_info)
                if mapped != term:
                    sql = re.sub(rf'\b{term}\b', mapped, sql, flags=re.IGNORECASE)

        if "employee" in user_input.lower():
            sql = re.sub(r'\bFROM\s+table\b', 'FROM employee', sql, flags=re.IGNORECASE)
            sql = re.sub(r'\b(?:table|employee|emp)\b', 'Employee', sql, flags=re.IGNORECASE)
            sql = re.sub(r'\b(?:emp_?id)\b', 'EmpID', sql, flags=re.IGNORECASE)
            sql = re.sub(r'\b(?:salaries?|earnings?|pay|compensation)\b', 'Salary', sql, flags=re.IGNORECASE)

            sql = re.sub(r'\bSELECT\s+(Employees|Employee)\b', 'SELECT EmpID, Salary', sql, flags=re.IGNORECASE)
            sql = re.sub(r'\b(Employees|Employee)\b', 'EmpID, Salary', sql, flags=re.IGNORECASE)

            sql = re.sub(r'\bEarnings\s*\(\s*\$\s*\)', 'Salary', sql, flags=re.IGNORECASE)
            sql = re.sub(r'\bEarnings\b', 'Salary', sql, flags=re.IGNORECASE)
            sql = re.sub(r'\bPay\b|\bCompensation\b', 'Salary', sql, flags=re.IGNORECASE)

            sql = re.sub(r'\bEmployee\b', 'employee', sql, flags=re.IGNORECASE)

            sql = re.sub(r'WHERE\s+\w+\s*\(\s*\$\s*\)\s*([><+=]+)\s*(\d+)', r'WHERE Salary \1 \2', sql, flags=re.IGNORECASE)

            numbers = [num.replace(',', '').replace('₹', '') for num in re.findall(r'(\d[\d,\.]*)', user_input)]

            between_match = re.search(r'(between|from)\s+(\d[\d,\.]*)\s+(and|to|-)\s+(\d[\d,\.]*)', user_input, re.IGNORECASE)
            if between_match and len(numbers) >= 2:
                low, high = numbers[:2]
                sql = re.sub(r'WHERE\s+Salary\s*[<>!=]+\s*\d+', '', sql, flags=re.IGNORECASE)
                sql = re.sub(r'BETWEEN\s+\d+\s+AND\s+\d+', f'BETWEEN {low} AND {high}', sql, flags=re.IGNORECASE)
                if "BETWEEN" not in sql:
                    sql = re.sub(r'(WHERE\s+)?Salary\s*', f'WHERE Salary BETWEEN {low} AND {high}', sql)
            elif numbers:
                num = numbers[0]
                operator = "="
                if re.search(r'less\s+than|under|below', user_input, re.IGNORECASE):
                    operator = "<"
                elif re.search(r'greater\s+than|more\s+than|above', user_input, re.IGNORECASE):
                    operator = ">"

                sql = re.sub(r'Salary\s*\(\s*\$\s*\)', 'Salary', sql, flags=re.IGNORECASE)
                sql = re.sub(r'WHERE\s+[^=<>]*\(\s*\$\s*\)', '', sql, flags=re.IGNORECASE)

                sql = re.sub(r'Salary\s*[<>!=]?\s*\d+', f'Salary {operator} {num}', sql, flags=re.IGNORECASE)
                if not re.search(r'Salary\s*[<>!=]=?\s*\d+', sql):
                    sql = re.sub(r'\bSalary\b(?!\s*[<>!=])', f'Salary {operator} {num}', sql, flags=re.IGNORECASE)

        sql = re.sub(r'\bFROM\s+(EmpID\s*,\s*Salary|Employees?)\b', 'FROM employee', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\bFROM\s+Employee\b', 'FROM employee', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\bJOIN\s+Employee\b', 'JOIN employee', sql, flags=re.IGNORECASE)

        sql = re.sub(r'(FROM\s+\w+).*\1', r'\1', sql, flags=re.IGNORECASE)
        sql = re.sub(r'(WHERE\s+Salary\s+BETWEEN\s+\d+\s+AND\s+\d+).*\1', r'\1', sql, flags=re.IGNORECASE)
        sql = re.sub(r'(SELECT\s+[^\s]+,?\s*)\s*WHERE', r'\1 FROM employee WHERE', sql, flags=re.IGNORECASE)
        sql = re.sub(r'FROM\s+[^ ]+\s+FROM', 'FROM', sql, flags=re.IGNORECASE)
        sql = re.sub(r'WHERE\s+[^ ]+\s+WHERE', 'WHERE', sql, flags=re.IGNORECASE)

        if not re.search(r'\bSELECT\b', sql, re.IGNORECASE):
            sql = "SELECT EmpID, Salary " + sql
        if not re.search(r'\bFROM\b', sql, re.IGNORECASE):
            sql = re.sub(r'(EmpID, Salary)', r'\1 FROM employee', sql, count=1, flags=re.IGNORECASE)

        sql = re.sub(r'SELECT\s+([^,]+),\s+FROM', r'SELECT \1 FROM', sql, flags=re.IGNORECASE)
        sql = re.sub(r'(BETWEEN\s+\d+\s+AND\s+\d+)[^\s]*', r'\1', sql, flags=re.IGNORECASE)

        if re.search(r'SELECT\s+FROM', sql, re.IGNORECASE):
            sql = re.sub(r'SELECT\s+FROM', 'SELECT EmpID, Salary FROM', sql, flags=re.IGNORECASE)

        if re.match(r'^\s*SELECT\s*,?\s*FROM', sql, re.IGNORECASE):
            sql = re.sub(r'SELECT\s*,?\s*FROM', 'SELECT EmpID, Salary FROM', sql, flags=re.IGNORECASE)

        if re.match(r'^\s*SELECT\s+EmpID\s+FROM', sql, re.IGNORECASE):
            sql = re.sub(r'SELECT\s+EmpID\s+FROM', 'SELECT EmpID, Salary FROM', sql, flags=re.IGNORECASE)

        sql = re.sub(r'(BETWEEN\s+\d+\s+AND\s+\d+).*=.*', r'\1', sql, flags=re.IGNORECASE)

        is_valid, error_msg = is_valid_select(sql)
        if not is_valid:
            return f"ERROR: {error_msg}"

        return sql
    except Exception as e:
        return f"ERROR: SQL cleaning failed - {str(e)}"


# ✅ Final callable function
def generate_sql(natural_language):
    try:
        schema_info = {}
        if "Schema:" in natural_language and "Question:" in natural_language:
            parts = natural_language.split("Question:", 1)
            schema_str = parts[0].replace("Schema:", "").strip()
            natural_language = parts[1].strip()
            schema_info = parse_schema(schema_str)

        input_text = f"translate English to SQL: {natural_language}"
        sql_raw = hf_generate(input_text)

        cleaned_sql = clean_sql(sql_raw, natural_language, schema_info)
        if cleaned_sql.startswith("ERROR:"):
            return cleaned_sql
        return cleaned_sql
    except Exception as e:
        return f"ERROR: SQL generation failed - {str(e)}"
