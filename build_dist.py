import os

def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def build():
    base_dir = '/home/matheus.hunsche/projects/hunsche/public-detective'
    showcase_dir = os.path.join(base_dir, 'showcase')
    dist_dir = os.path.join(base_dir, 'dist')
    
    html_content = read_file(os.path.join(showcase_dir, 'index.html'))
    css_content = read_file(os.path.join(showcase_dir, 'style.css'))
    js_content = read_file(os.path.join(showcase_dir, 'script.js'))
    data_content = read_file(os.path.join(showcase_dir, 'data.js'))
    
    # Inject CSS
    style_tag = f'<style>\n{css_content}\n</style>'
    html_content = html_content.replace('<link rel="stylesheet" href="style.css">', style_tag)
    
    # Inject Data and Script
    # Remove existing script tags
    html_content = html_content.replace('<script src="data.js"></script>', '')
    html_content = html_content.replace('<script src="script.js"></script>', '')
    
    # Add inline scripts before closing body
    scripts = f'<script>\n{data_content}\n</script>\n<script>\n{js_content}\n</script>'
    html_content = html_content.replace('</body>', f'{scripts}\n</body>')
    
    output_path = os.path.join(dist_dir, 'index.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Build complete: {output_path}")

if __name__ == '__main__':
    build()
