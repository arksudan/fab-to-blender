import argparse
import json
import os
import sys
import time
from PIL import Image
import cloudscraper
import requests

headers = {
    "Accept": "application/json, text/plain, */*",
    # Let requests negotiate compression. Explicitly advertising zstd caused
    # undecodable responses in some Blender Python environments.
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/132 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
}

querystring = {
    "is_free": "1",
    # Fab renamed the seller from "Quixel" to "Quixel Megascans".
    "seller": "Quixel Megascans",
    "sort_by": "-firstPublishedAt"  # Default sort
}


def crop_thumbnails(image_path):
    if image_path:
        image = Image.open(f"{image_path}")
        # Get the original dimensions
        width, height = image.size
        new_width = height
        top = 0
        bottom = height
        left = (width - new_width) // 2
        right = left + new_width
        # Crop the image
        cropped_image = image.crop((left, top, right, bottom))
        cropped_image.save(f"{image_path}")


def smart_square_crop(image_path, border_width=40):
    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    target_color = (32, 32, 32)
    pixels = image.load()

    top, bottom, left, right = 0, height, 0, width

    # Scan from top
    for y in range(height):
        if any(pixels[x, y] != target_color for x in range(width)):
            top = y
            break

    # Scan from bottom
    for y in range(height - 1, -1, -1):
        if any(pixels[x, y] != target_color for x in range(width)):
            bottom = y + 1
            break

    # Scan from left
    for x in range(width):
        if any(pixels[x, y] != target_color for y in range(height)):
            left = x
            break

    # Scan from right
    for x in range(width - 1, -1, -1):
        if any(pixels[x, y] != target_color for y in range(height)):
            right = x + 1
            break

    # Apply border
    top = max(0, top - border_width)
    bottom = min(height, bottom + border_width)
    left = max(0, left - border_width)
    right = min(width, right + border_width)

    cropped_width = right - left
    cropped_height = bottom - top
    new_size = max(cropped_width, cropped_height)
    left_offset = (new_size - cropped_width) // 2
    top_offset = (new_size - cropped_height) // 2

    # Create a new square image with the target color
    new_image = Image.new("RGB", (new_size, new_size), target_color)
    cropped = image.crop((left, top, right, bottom))
    new_image.paste(cropped, (left_offset, top_offset))

    new_image.save(image_path)


def fetch_assets(url, referer, data_dir, asset_type=None, query=None, cursor=None, sort_method=None):
    headers["Referer"] = referer
    querystring["cursor"] = cursor
    querystring["listing_types"] = asset_type
    if asset_type == "3d-model":
        querystring["asset_formats"] = "fbx"
    if asset_type == "material":
        querystring["asset_formats"] = "texture-set"
    querystring["q"] = query

    # Map sort_method to the appropriate API sort_by parameter
    sort_mapping = {
        'newest': '-firstPublishedAt',
        'oldest': 'firstPublishedAt',
        'title_asc': 'title',
        'title_desc': '-title'
    }
    querystring["sort_by"] = sort_mapping.get(sort_method, '-firstPublishedAt')

    file_path = os.path.join(data_dir, f"search_v3_{asset_type}_{query}_{sort_method}_{cursor}.json")

    fetcher(url, headers, file_path, query=querystring)


def fetch_asset_formats(url, referer, data_dir, asset_uid=None):
    headers["Referer"] = referer
    file_path = os.path.join(data_dir, f"asset_{asset_uid}.json")

    fetcher(url, headers, file_path)


def fetch_down_link(url, referer, data_dir, asset_uid=None):
    headers["Referer"] = referer
    file_path = os.path.join(data_dir, f"downlink_{asset_uid}.json")

    fetcher(url, headers, file_path)


def fetcher(url, header, file_path, query=None):
    max_retries = 5  # Number of retries
    retry_delay = 2  # Delay in seconds between retries
    for attempt in range(1, max_retries + 1):
        try:
            # Fab's public catalog endpoints do not need a browser login.
            # Use the standard client to avoid the former zstd decoding issue.
            response = requests.get(url, headers=header, params=query, timeout=30)

            if response.status_code == 200:
                # Success: Process the response
                try:
                    json_data = response.json()
                    pretty_json = json.dumps(json_data, indent=2)

                    # Save the pretty-printed data to a file
                    with open(file_path, 'w') as f:
                        f.write(pretty_json)
                    print(f"Data saved to {file_path}")
                    return  # Exit the function on success

                except ValueError as exc:
                    if "cloudflare" in response.text.lower() or "<html" in response.text[:500].lower():
                        raise RuntimeError(
                            "Fab returned a browser challenge. Retry later or check your network connection.") from exc
                    raise RuntimeError("Fab returned a response that is not JSON.") from exc

            elif response.status_code == 403:
                # Forbidden: Log and retry
                print(f"Attempt {attempt}: Received 403 Forbidden. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                continue

            else:
                # Other HTTP errors
                raise RuntimeError(f"Fab returned HTTP {response.status_code}.")

        except Exception as e:
            print(f"Attempt {attempt}: Request failed with exception: {e}. Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
            continue

    raise RuntimeError("Fab request failed after all retry attempts.")


def download_file(url, out_file):
    print("Downloading file...")
    # Create the cloudscraper instance
    scraper = cloudscraper.create_scraper()
    response = scraper.get(url, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get('content-length', 0))
    downloaded_size = 0

    # Determine chunk size dynamically
    if total_size < 1_000_000:  # Less than 1 MB
        chunk_size = 8192  # 8 KB
    elif total_size < 100_000_000:  # 1 MB to 100 MB
        chunk_size = 65536  # 64 KB
    else:  # Greater than 100 MB
        chunk_size = 262144  # 256 KB

    with open(out_file, 'wb') as file:
        for chunk in response.iter_content(chunk_size=chunk_size):
            file.write(chunk)
            downloaded_size += len(chunk)
            if total_size > 0:
                progress = (downloaded_size / total_size) * 100
                print(f"Download Progress: {progress:.2f}%")
            else:
                print("Download Progress: Unknown file size")

    print(f"File downloaded successfully and saved as '{out_file}'.")


def main(function_name, *args):
    if function_name == "crop_thumbnails":
        crop_thumbnails(*args)
    elif function_name == "fetch_assets":
        fetch_assets(*args)
    elif function_name == "fetch_asset_formats":
        fetch_asset_formats(*args)
    elif function_name == "fetch_down_link":
        fetch_down_link(*args)
    elif function_name == "download_file":
        download_file(*args)
    elif function_name == "smart_square_crop":
        smart_square_crop(*args)
    else:
        print("Function not found")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--function", required=True, help="Name of the function to run")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments for the function")
    args = parser.parse_args()
    main(args.function, *args.args)

