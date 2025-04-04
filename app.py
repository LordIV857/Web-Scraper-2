import os
from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

app = Flask(__name__)

@app.route('/scrape', methods=['GET'])
def scrape():
    url = request.args.get('url')

    if not url:
        return jsonify({'error': 'URL parameter is missing'}), 400

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as e:
        return jsonify({'error': f'Failed to fetch the page: {str(e)}'}), 500

    soup = BeautifulSoup(response.text, 'html.parser')

    # Nom du site
    title = soup.title.string.strip() if soup.title else ''
    og_site_name = soup.find('meta', property='og:site_name')
    site_name = og_site_name['content'] if og_site_name else title

    # Image représentative
    og_image = soup.find('meta', property='og:image')
    icon_link = soup.find('link', rel=lambda x: x and 'icon' in x.lower())

    image_url = ''
    if og_image and og_image.get('content'):
        image_url = og_image['content']
    elif icon_link and icon_link.get('href'):
        icon_href = icon_link['href']
        parsed = urlparse(url)
        if icon_href.startswith('http'):
            image_url = icon_href
        else:
            image_url = f"{parsed.scheme}://{parsed.netloc}{icon_href}"

    return jsonify({
        'url': url,
        'site_name': site_name,
        'image': image_url,
        'html': response.text  # ou optionnel : soup.prettify()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)