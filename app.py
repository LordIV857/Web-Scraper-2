import os
import base64
import requests
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from urllib.parse import urlparse

app = Flask(__name__)

# Fonction pour extraire le nom du site sans l'extension (.fr, .com, etc.)
def extract_site_name(url):
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.replace("www.", "").split('.')[0]
    return domain.capitalize()

# Fonction pour convertir une image en base64
def image_to_base64(image_url):
    try:
        # Télécharger l'image
        response = requests.get(image_url)
        response.raise_for_status()
        
        # Convertir l'image en base64
        image_base64 = base64.b64encode(response.content).decode('utf-8')
        return f"data:image/png;base64,{image_base64}"
    except requests.exceptions.RequestException:
        return None

@app.route('/scrape', methods=['GET'])
def scrape():
    url = request.args.get('url')

    if not url:
        return jsonify({'error': 'URL parameter is missing'}), 400

    try:
        # Récupérer le HTML de la page
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as e:
        return jsonify({'error': f'Failed to fetch the page: {str(e)}'}), 500

    soup = BeautifulSoup(response.text, 'html.parser')

    # Nom du site (extraction sans ".fr", ".com", etc.)
    site_name = extract_site_name(url)

    # Image représentative
    image_url = ''
    og_image = soup.find('meta', property='og:image')
    icon_link = soup.find('link', rel=lambda x: x and 'icon' in x.lower())

    # Si l'image Open Graph est présente
    if og_image and og_image.get('content'):
        image_url = og_image['content']
    elif icon_link and icon_link.get('href'):
        # Si on a une icône, construire l'URL complète
        icon_href = icon_link['href']
        parsed = urlparse(url)
        if icon_href.startswith('http'):
            image_url = icon_href
        else:
            image_url = f"{parsed.scheme}://{parsed.netloc}{icon_href}"

    # Si l'URL de l'image est valide, la convertir en base64
    if image_url:
        image_base64 = image_to_base64(image_url)
        if image_base64:
            image_url = image_base64
        else:
            image_url = None

    # Préparer la réponse sous forme de liste d'objets
    return jsonify([{
        "url": url,
        "site_name": site_name,
        "image": image_url,
        #"html": response.text  # ou soup.prettify() pour une version plus lisible
    }])

if __name__ == '__main__':
    app.run(debug=True)
