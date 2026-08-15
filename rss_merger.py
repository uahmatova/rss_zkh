import datetime
import requests
import re
import time
from xml.etree import ElementTree as ET
import os
VK_TOKEN = os.getenv('VK_TOKEN')

# --- НАСТРОЙКА ---
VK_GROUPS = [

] 

#VK_TOKEN = 'd0aba882d0aba882d0aba8829cd39c235edd0abd0aba882b82c14340f4c8b620425b030'
POSTS_PER_GROUP = 30
DAYS_BACK = 7  # Брать посты только за последние 7 дней

# --- ФУНКЦИЯ ВЫДЕЛЕНИЯ ПЕРВОГО ПРЕДЛОЖЕНИЯ ---
def get_first_sentence(text):
    """
    Извлекает первое предложение из текста.
    Предложение заканчивается на . ! ? или с новой строки.
    """
    if not text:
        return ""
    
    # Ищем первый знак конца предложения (. ! ?) или конец строки
    # Ищем позицию первого из символов: . ! ? или \n
    end_pos = -1
    for symbol in ['.', '!', '?', '\n']:
        pos = text.find(symbol)
        if pos != -1:
            if end_pos == -1 or pos < end_pos:
                end_pos = pos
    
    if end_pos != -1:
        # Берем текст до найденного символа + сам символ
        first_sentence = text[:end_pos + 1].strip()
        # Если это точка, и она часть числа (например, "1.5"), ищем дальше
        if first_sentence.endswith('.') and len(first_sentence) > 1 and first_sentence[-2].isdigit():
            # Пропускаем эту точку, ищем следующую
            second_try = get_first_sentence(text[end_pos + 1:])
            if second_try:
                return first_sentence + ' ' + second_try
        return first_sentence
    else:
        # Если нет знаков препинания, берем первые 100 символов
        return text[:100].strip()

# # --- ФУНКЦИЯ ОЧИСТКИ ОПИСАНИЯ ---
# def clean_description(text):
#     if not text:
#         return ""
#     phrases_to_remove = [
#         'Подписывайтесь на нас в Telegram',
#         'Подписывайтесь на нас в Max',
#         'Подписывайтесь на нас в Telegram и Max',
#         'Подписывайтесь на нас в соцсетях',
#         'Читайте нас в Telegram',
#         'Подписывайтесь на нас в социальных сетях',
#     ]
#     for phrase in phrases_to_remove:
#         text = text.replace(phrase, '').strip()
#     text = re.sub(r'\s+', ' ', text)
#     return text.strip()

# --- ФУНКЦИЯ ПОЛУЧЕНИЯ ПОСТОВ ---
def fetch_vk_posts(group_id, token, count=30, days_back=7):
    print(f"Обработка группы: {group_id}")
    try:
        threshold_time = int(time.time()) - days_back * 24 * 60 * 60
        
        url = "https://api.vk.ru/method/wall.get"
        params = {
            "access_token": token,
            "v": "5.131",
            "count": count,
            "extended": 0,
        }
        
        if isinstance(group_id, int):
            params["owner_id"] = group_id
        else:
            params["domain"] = group_id
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if "error" in data:
            print(f"  Ошибка VK API: {data['error']['error_msg']}")
            return []
        
        items = data.get("response", {}).get("items", [])
        print(f"  Получено {len(items)} постов")
        
        posts = []
        for item in items:
            # Пропускаем посты старше порога
            if item['date'] < threshold_time:
                continue
                
            text = item.get("text", "")
            if not text:
                continue
            
            # Извлекаем картинку
            image_url = None
            for attachment in item.get("attachments", []):
                if attachment.get("type") == "photo":
                    photo = attachment.get("photo", {})
                    if "sizes" in photo:
                        sizes = sorted(photo["sizes"], key=lambda x: x.get("width", 0), reverse=True)
                        if sizes:
                            image_url = sizes[0].get("url")
                    else:
                        image_url = photo.get("src_big") or photo.get("src") or photo.get("src_xbig")
                    if image_url:
                        break
                elif attachment.get("type") == "link" and not image_url:
                    link_photo = attachment.get("link", {}).get("photo")
                    if link_photo:
                        image_url = link_photo.get("src_big") or link_photo.get("src")
            
            pub_date = datetime.datetime.fromtimestamp(item['date']).strftime("%a, %d %b %Y %H:%M:%S +0500")
            post_link = f"https://vk.ru/wall{item['owner_id']}_{item['id']}"
            
            description = text
            
            # --- ФОРМИРУЕМ ЗАГОЛОВОК ИЗ ПЕРВОГО ПРЕДЛОЖЕНИЯ ---
            title = get_first_sentence(text)
            # Если заголовок получился слишком длинным, обрезаем до 150 символов
            if len(title) > 150:
                title = title[:150].strip() + "..."
            
            posts.append({
                'title': title,
                'link': post_link,
                'description': description,
                'pub_date': pub_date,
                'image': image_url,
                'source': f"ВК (группа {group_id})"
            })
        
        print(f"  Отфильтровано {len(posts)} постов за последние {days_back} дней")
        return posts
    
    except Exception as e:
        print(f"  ОШИБКА при загрузке {group_id}: {e}")
        return []

# --- 1. Собираем посты ---
all_news = []
for group_id in VK_GROUPS:
    news_from_group = fetch_vk_posts(group_id, VK_TOKEN, POSTS_PER_GROUP, DAYS_BACK)
    all_news.extend(news_from_group)

print(f"Всего собрано {len(all_news)} постов.")

# --- 2. Сортируем по дате ---
def parse_date(date_string):
    if not date_string:
        return datetime.datetime(1970, 1, 1)
    try:
        return datetime.datetime.strptime(date_string, "%a, %d %b %Y %H:%M:%S %Z")
    except:
        try:
            return datetime.datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        except:
            return datetime.datetime.now()

all_news.sort(key=lambda x: parse_date(x['pub_date']), reverse=True)

# --- 3. Создаем RSS-файл ---
rss_root = ET.Element("rss", version="2.0")
channel = ET.SubElement(rss_root, "channel")

ET.SubElement(channel, "title").text = "Объединенная лента новостей"
ET.SubElement(channel, "description").text = "Новости из групп ВКонтакте: permkrai20 и minzdrav_permkrai"

for item in all_news:
    item_element = ET.SubElement(channel, "item")
    ET.SubElement(item_element, "title").text = item['title']
    ET.SubElement(item_element, "link").text = item['link']

    desc_element = ET.SubElement(item_element, "description")
    desc_element.text = item['description']

    pub_element = ET.SubElement(item_element, "pubDate")
    pub_element.text = str(item['pub_date'])

    if item.get('image'):
        enclosure = ET.SubElement(item_element, "enclosure")
        enclosure.set('url', item['image'])
        enclosure.set('type', 'image/jpeg')

tree = ET.ElementTree(rss_root)
tree.write('merged_feed.xml', encoding='utf-8', xml_declaration=True)

print(f"✅ RSS-лента создана с {len(all_news)} постами!")
