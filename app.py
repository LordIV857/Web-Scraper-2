import requests
import re
import os
from flask import Flask, request, jsonify
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

app = Flask(__name__)

# Headers utilisés pour simuler un vrai navigateur et éviter les blocages de certains sites
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}

@app.route('/scrape', methods=['GET'])
def scrape():
    """
    Endpoint principal : reçoit une URL et une liste de mots-clés, puis retourne les liens d'articles valides.
    """
    url = request.args.get('url')
    keywords = request.args.get('keywords')
    logic = request.args.get('logic', 'ou').lower()

    # Remplacer les antislashs par des slashs
    url = url.replace('\\', '/')

    # Vérifie que l'URL est bien fournie
    if not url:
        return jsonify({'error': 'URL parameter is missing'}), 400

    # Vérifie que les mots-clés sont bien fournis
    if not keywords:
        return jsonify({'error': 'Keywords parameter is missing'}), 400

    # Nettoyage et transformation des mots-clés
    keywords_list = [kw.strip().lower() for kw in keywords.split(',') if kw.strip()]
    if not keywords_list:
        return jsonify({'error': 'No valid keywords provided'}), 400

    # Extraction des liens d'articles correspondant aux mots-clés
    article_links = extract_article_links(url, keywords_list, logic)

    if not article_links:
        return jsonify({'error': 'No valid article links found'}), 404

    # Récupération du nom du site
    site_name = extract_site_name(url)

    # Faire une requête pour obtenir le HTML de la page et extraire l'image
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        image_url = extract_image(soup, url)
        meta_site_name = extract_site_name_from_meta(soup)
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors du téléchargement de la page: {e}")
        image_url = None
        meta_site_name = None

    return jsonify({
        "site_name": meta_site_name or site_name or None,  # Si le nom n'est pas trouvé, on renvoie None
        "site_image": image_url or None,      # Si l'image n'est pas trouvée, on renvoie None
        "article_links": article_links,
    })

def extract_article_links(url, keywords, logic):
    """
    Scrape la page pour extraire les liens vers des articles contenant les mots-clés.
    """
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # On supprime les balises de navigation, en-tête et pied de page pour éviter le bruit
        for tag in soup.find_all(['nav', 'header', 'footer']):
            tag.decompose()

        links = []

        # Recherche de tous les liens <a>
        for a_tag in soup.find_all('a', href=True):
            # On ignore les liens à l'intérieur des titres pour éviter les doublons non pertinents
            if a_tag.find_parent(['h3', 'h4', 'h5', 'h6']):
                continue

            link = a_tag['href']
            absolute_link = urljoin(url, link)

            # Vérifie que le lien est interne et ressemble à un article
            if is_internal_link(url, absolute_link) and is_article_link(absolute_link):
                article_title = extract_article_title_from_link(a_tag)
                img_tag = extract_image_from_parent(a_tag)

                # Si le titre, l'image et les mots-clés correspondent, on ajoute le lien
                if article_title and img_tag and is_valid_article(absolute_link, article_title, keywords, logic):
                    img_url = get_image_url(img_tag, url)
                    if img_url:
                        links.append({'url': absolute_link, 'title': article_title, 'image': img_url})

        return links

    except requests.exceptions.RequestException as e:
        print(f"Erreur lors du téléchargement de la page: {e}")
        return []

def is_valid_article(url, title, keywords, logic):
    """
    Vérifie si l'article contient les mots-clés dans l'URL ou le titre, selon la logique 'et' ou 'ou'.
    """
    url_lower = url.lower()
    title_lower = title.lower()

    if logic == 'et':
        return all(keyword in url_lower or keyword in title_lower for keyword in keywords)
    elif logic == 'ou':
        return any(keyword in url_lower or keyword in title_lower for keyword in keywords)
    else:
        return False

def extract_article_title_from_link(a_tag):
    """
    Tente d'extraire le titre d'un article à partir du contenu textuel du lien.
    """
    texts = [child.get_text(strip=True) for child in a_tag.find_all(True) if child.get_text(strip=True)]

    if not texts:
        return None

    longest_text = max(texts, key=len)

    # Divise le texte lorsqu'une minuscule est suivie d'une majuscule
    segments = re.split(r'(?<=[a-z])(?=[A-Z])', longest_text)

    # Retourne le segment le plus long
    return max(segments, key=len) if segments else longest_text

def is_internal_link(base_url, link):
    """
    Vérifie si un lien est interne au domaine d'origine.
    """
    base_domain = urlparse(base_url).netloc
    link_domain = urlparse(link).netloc
    return base_domain == link_domain

def is_article_link(link):
    """
    Heuristiques pour savoir si un lien est probablement un article.
    """
    file_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.zip']
    if any(link.endswith(ext) for ext in file_extensions):
        return False

    if len(link) < 20:
        return False

    exclude_paths = ['search', 'category', 'blog']
    path = urlparse(link).path
    if any(exclude in path.lower() for exclude in exclude_paths):
        return False

    if "-" not in link or "#" in link:
        return False

    return True

def extract_image_from_parent(a_tag):
    """
    Tente de trouver une image associée au lien dans son parent HTML.
    """
    parent = a_tag.find_parent()

    img_tag = parent.find('img')

    # Si on ne trouve pas directement, on fouille plus loin dans la hiérarchie
    if not img_tag:
        for element in parent.find_all(True):
            img_tag = element.find('img')
            if img_tag:
                return img_tag

    if img_tag:
        return img_tag

    return None

def get_image_url(img_tag, base_url):
    """
    Récupère l'URL absolue d'une image à partir d'un tag <img>.
    """
    srcset = img_tag.get('srcset')
    img_url = None
    
    if srcset:
        # Prend la dernière image du srcset (souvent la plus grande)
        srcset_urls = [url.strip().split(' ')[0] for url in srcset.split(', ')]
        img_url = srcset_urls[-1]

    if not img_url:
        # Fallback : src ou data-src
        img_url = img_tag.get('data-src') or img_tag.get('src')

    # Convertir l'URL relative en absolue
    if img_url and img_url.startswith('/'):
        img_url = urljoin(base_url, img_url)

    return img_url

def extract_site_name(url):
    """
    Extraction du nom du site à partir de l'URL.
    Si le nom contient un caractère spécial, il est nettoyé.
    """
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.replace("www.", "").split('.')[0]
    
    # Supprime les caractères spéciaux après le premier caractère alphanumérique
    if domain:
        domain = re.sub(r'[^a-zA-ZÀ-ÿ\s-]', '', domain)  # Garder seulement les caractères alphabétiques et les accents
        return domain.capitalize()

    return None

def extract_site_name_from_meta(soup):
    """
    Recherche du nom du site dans les balises meta.
    Si un nom de site est trouvé, il est nettoyé des caractères spéciaux
    et de tout ce qui vient après . _ ou -.
    """
    meta_site_name_tag = soup.find('meta', property='og:site_name')
    if meta_site_name_tag and 'content' in meta_site_name_tag.attrs:
        site_name = meta_site_name_tag.attrs['content']
        # Enlève tout ce qui vient après un des caractères spéciaux . _ ou -
        site_name = re.sub(r'[._-].*$', '', site_name)
        return site_name
    
    return None

def extract_image(soup, base_url):
    """
    Extraction de l'image associée au site via favicon ou OG image.
    Retourne None si aucune image n'est trouvée.
    """
    # Cherche dans la balise <link rel="icon"> pour le favicon
    favicon_tag = soup.find('link', rel='icon')
    if favicon_tag and 'href' in favicon_tag.attrs:
        favicon_url = favicon_tag.attrs['href']
        # Si l'URL est relative, on la convertit en absolue
        return urljoin(base_url, favicon_url)

    # Cherche dans la balise <meta property="og:image"> pour l'image Open Graph
    og_image_tag = soup.find('meta', property='og:image')
    if og_image_tag and 'content' in og_image_tag.attrs:
        return og_image_tag.attrs['content']

    # Si aucune image n'est trouvée, on retourne None
    return None

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
