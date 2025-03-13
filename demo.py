from flask import Flask, request, jsonify, render_template
import singlestoredb as s2

app = Flask(__name__)

def get_connection():
    """
    Establish a connection to your SingleStore cloud instance.
    Replace these placeholders with your actual credentials.
    개인의 VM에 SingleStore 설치 후 하셔도 가능합니다.
    VM 사용 시 CREATE DATABASE {Db name};
    DB 생성 후 사용하시면 됩니다.
    """
    return s2.connect(
        host='{IP:Port}',
        user='{DB user}',
        password='{Password}',
        database='{Db name}'
    )

def setup_schema():
    """
    1. Drops any existing 'products' table.
    2. Creates a 'products' table with an n-gram FULLTEXT index (Version 2).
       - minGramSize=2, maxGramSize=5
       - lower_case token filter
    3. Inserts sample data and flushes the index.
    !! 한글화 하며 minGramSize=1 maxGramSize=4로 변경했습니다.
    !! token filter를 삭제 했습니다.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS products;")
    create_table_query = """
    CREATE TABLE products (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255),
        select_count INT DEFAULT 0,
        FULLTEXT USING VERSION 2 (name)
            INDEX_OPTIONS '{
                "analyzer": {
                    "custom": {
                        "tokenizer": {
                            "n_gram": {
                                "minGramSize": 1,
                                "maxGramSize": 4
                            }
                        }
                    }
                }
            }'
    );
    """
    cursor.execute(create_table_query)

    """
    예제를 한글로 변경했습니다.
    """
    # Sample data
    sample_products = [
        "아이폰", "아이패드", "아이맥",
        "아이팟", "갤럭시", "노키아",
        "화웨이", "블랙베리", "크롬",
        "에어팟", "버즈", "갤럭시 워치",
        "애플 워치", "갤럭시 플립", "갤럭시 폴드"
    ]
    insert_query = "INSERT INTO products (name) VALUES (%s)"
    for product in sample_products:
        cursor.execute(insert_query, (product,))
    conn.commit()

    # Force the FULLTEXT index to refresh
    cursor.execute("OPTIMIZE TABLE products FLUSH;")
    cursor.close()
    conn.close()
    print("Schema setup and sample data population complete.")

def get_autocomplete_suggestions(user_input):
    """
    Returns autocomplete suggestions by combining:
      1. N-gram prefix search (BM25 too, but used in a prefix expression).
      2. If few matches, a fuzzy search (~1) with BM25 for ranking.
    
    Importantly, we do NOT use MATCH(...) AGAINST(...) because we want to
    avoid the syntax errors with BM25 + fuzzy + n-gram. Instead, we directly
    use BM25(table_name, 'search_expression').
    
    For prefix matching with BM25, we can still specify 'name:ip*' or 'name:ip*'?
    However, SingleStore doesn't support a leading wildcard. We'll do something
    simpler: just check for any tokens that contain user_input (for an example).
    
    (Alternatively, we can just do a standard BM25 with your typed input and
    let the n-gram index handle it as a partial match.)
    """
    conn = get_connection()
    cursor = conn.cursor()

    suggestions = []

    # Always do a normal n-gram BM25 search
    prefix_expr = f"name:{user_input}"
    prefix_query = f"""
        SELECT name, (BM25(products, '{prefix_expr}')) * 0.9 + select_count * 0.1 AS score,  select_count
        FROM products
        WHERE BM25(products, '{prefix_expr}') > 0
        ORDER BY score DESC
        LIMIT 10;
    """
    cursor.execute(prefix_query)
    for (name, score, select_count) in cursor.fetchall():
        suggestions.append({"name": name, "select_count": select_count})

    # If fewer than 5 suggestions and user_input >= 4 chars, do fuzzy
    if len(suggestions) < 5 and len(user_input) >= 4:
        fuzzy_expr = f"name:{user_input}~1"
        fuzzy_query = f"""
            SELECT name, (BM25(products, '{fuzzy_expr}')) * 0.9 + select_count * 0.1 AS score,  select_count
            FROM products
            WHERE BM25(products, '{fuzzy_expr}') > 0
            ORDER BY score DESC
            LIMIT 10;
        """
        cursor.execute(fuzzy_query)
        for (name, score, select_count) in cursor.fetchall():
            if name not in suggestions:
                suggestions.append({"name": name, "select_count": select_count})

    cursor.close()
    conn.close()
    return suggestions

@app.route('/')
def index():
    """Renders a simple page with an input box."""
    return render_template('index.html')

@app.route('/autocomplete')
def autocomplete():
    term = request.args.get('term', '')
    suggestions = get_autocomplete_suggestions(term)
    # Just return the top suggestion if it starts with the term (case-insensitive).
    """
    가장 높은 결과 중 하나를 Ghost로 보여줘 tab을 누를시 자동완성이 되게하는 예제에서
    자동완성 추천 검색 결과 최대 상위 10개를 검색창 밑의 리스트로 보여주는 것으로 변경했습니다.
    리스트 단어 클릭시 자동완성 가능합니다.
    """
    return jsonify({"suggestions": suggestions})

@app.route('/increment_count', methods=['POST'])
def increment_count():
    term = request.json.get('term')
    if not term:
        return jsonify({'error': 'Term is required'}), 400
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # 먼저 해당 이름이 존재하는지 확인
        check_query = "SELECT COUNT(*) FROM products WHERE name = %s"
        cursor.execute(check_query, (term,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            # 이름이 존재하면 select_count 증가
            update_query = """
            UPDATE products 
            SET select_count = select_count + 1 
            WHERE name = %s
            """
            cursor.execute(update_query, (term,))
        else:
            # 이름이 존재하지 않으면 새 레코드 삽입
            insert_query = """
            INSERT INTO products (name, select_count)
            VALUES (%s, 1)
            """
            cursor.execute(insert_query, (term,))
        
        cursor.execute("OPTIMIZE TABLE products FLUSH;")
        conn.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
        
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    setup_schema()
    app.run(debug=True)