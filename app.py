from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from collections import Counter

app = Flask(__name__)
CORS(app)  # Autorise les requêtes cross-origin (FlutterFlow)

@app.route('/scrape', methods=['GET'])
def scrape():
    # 1. Lire les paramètres
    url = request.args.get('url')
    keywords = request.args.get('keywords')
    logic = request.args.get('logic')

    print(f"[INFO] Paramètres reçus - url: {url}, keywords: {keywords}, logic: {logic}")

    if not url or not keywords or not logic:
        print("[ERROR] Paramètres manquants")
        return jsonify({"error": "Paramètres manquants"}), 400

    keyword_list = [kw.strip().lower() for kw in keywords.split(',')]
    logic = logic.lower()

    if logic not in ['et', 'ou']:
        print("[ERROR] Paramètre 'logic' invalide")
        return jsonify({"error": "Paramètre 'logic' invalide"}), 400

    try:
        # 2. Requête HTTP
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        print(f"[INFO] Requête HTTP faite, statut: {response.status_code}")

        if 'text/html' not in response.headers.get('Content-Type', ''):
            print("[ERROR] Le contenu n'est pas une page HTML")
            return jsonify({"error": "Le contenu n'est pas une page HTML"}), 400

        html = response.text
        soup = BeautifulSoup(html, 'html.parser')
        print("[INFO] HTML parsé")

        # 3. Extraire favicon
        favicon_tag = soup.find('link', rel=lambda x: x and 'icon' in x.lower())
        favicon_url = urljoin(url, favicon_tag['href']) if favicon_tag and favicon_tag.get('href') else ""
        print(f"[INFO] Favicon extrait : {favicon_url}")

        # 4. Nom du site = nom de domaine
        parsed_url = urlparse(url)
        site_name = parsed_url.hostname.replace('www.', '') if parsed_url.hostname else "Inconnu"
        print(f"[INFO] Nom du site : {site_name}")

        # 5. Extraire les chemins DOM des <img>
        img_paths = get_img_dom_paths(soup)
        print(f"[INFO] Nombre d'images trouvées: {len(img_paths)}")

        # 6. Filtrer les chemins pour détecter les blocs similaires
        filtered_paths = filter_paths_by_common_ancestors(img_paths)
        print(f"[INFO] Nombre de chemins filtrés: {len(filtered_paths)}")

        # 7. Trouver le niveau de séparation commun
        sep_index = find_separation_level(filtered_paths)
        print(f"[INFO] Niveau de séparation trouvé: {sep_index}")

        if sep_index is None:
            print("[WARNING] Aucun niveau de séparation trouvé")
            return jsonify({
                "article_links": [],
                "site_image": favicon_url,
                "site_name": site_name
            })

        # 8. Extraire les blocs d'article
        article_blocks = []
        for path in filtered_paths:
            if sep_index < 0:
                ancestor = path[sep_index]
            else:
                ancestor = path[sep_index]
            if ancestor not in article_blocks:
                article_blocks.append(ancestor)
        print(f"[INFO] Nombre de blocs d'article uniques extraits: {len(article_blocks)}")

        # 9. Extraire les infos des articles
        articles = []
        for idx, block in enumerate(article_blocks):
            info = extract_article_info(block, url, keyword_list)
            print(f"[DEBUG] Article {idx} - Titre: {info['title']} | URL: {info['url']} | Keywords trouvés: {info['keywords']}")

            # Appliquer la logique AND/OR sur les keywords
            if logic == 'et' and all(kw in info["keywords"] for kw in keyword_list):
                articles.append(info)
            elif logic == 'ou' and any(kw in info["keywords"] for kw in keyword_list):
                articles.append(info)

        print(f"[INFO] Nombre d'articles retenus après filtrage: {len(articles)}")

        # 10. Retourner les données finales
        return jsonify({
            "article_links": articles,
            "site_image": favicon_url,
            "site_name": site_name
        })

    except Exception as e:
        print(f"[EXCEPTION] {str(e)}")
        return jsonify({"error": f"Erreur lors du scraping : {str(e)}"}), 400


def get_img_dom_paths(soup):
    img_paths = []
    for img in soup.find_all('img'):
        path = []
        current = img
        while current:
            path.append(current)
            if current.name == 'html':
                break
            current = current.parent
        img_paths.append(path[::-1])
    return img_paths

def filter_paths_by_common_ancestors(img_paths):
    if not img_paths:
        return []
    
    max_len = max(len(p) for p in img_paths)
    filtered = [p for p in img_paths if len(p) == max_len]
    
    index = max_len - 1
    while index >= 0 and len(filtered) > 1:
        tags_at_index = [p[index].name for p in filtered]
        counter = Counter(tags_at_index)
        filtered = [p for p in filtered if counter[p[index].name] > 1]
        index -= 1
    return filtered

def find_separation_level(filtered_paths):
    if not filtered_paths:
        return None

    path_len = len(filtered_paths[0])
    for i in range(1, path_len + 1):
        tags_at_level = [p[-i].name for p in filtered_paths]
        if len(set(tags_at_level)) > 1:
            return -i + 1
    return -path_len

def extract_article_info(article_block, base_url, keywords):
    img = article_block.find('img')
    image_url = urljoin(base_url, img['src']) if img and img.has_attr('src') else None

    link = article_block.find('a', href=True)
    url = urljoin(base_url, link['href']) if link else None

    title = (link.get_text(strip=True) if link else article_block.get_text(strip=True)) or ""

    title_lower = title.lower()
    url_lower = url.lower() if url else ""
    found_keywords = []
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in title_lower or kw_lower in url_lower:
            found_keywords.append(kw)

    return {
        "image": image_url,
        "title": title,
        "url": url,
        "keywords": found_keywords
    }


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
