import os
import re

def update_file(path, client_name=None):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Update all badges to for-the-badge
    content = re.sub(r'(shields\.io/badge/[^-]+-[^-]+-[a-zA-Z0-9]+)\.svg([^\)]*)', r'\1.svg?style=for-the-badge', content)
    content = re.sub(r'(shields\.io/badge/[^\?]+\?)([^)]*)', lambda m: m.group(1) + (m.group(2) + "&style=for-the-badge" if "style=" not in m.group(2) else m.group(2).replace("style=flat", "style=for-the-badge")), content)
    
    # Replace old nerve_hub.jpg with SVG depending on context
    if client_name == "hub":
        content = content.replace("nerve_hub.jpg", "assets/nerve_hub.svg")
    elif client_name == "python":
        content = content.replace("nerve_hub.jpg", "../../assets/python_client.svg")
        # Ensure it has an image if it didn't
        if "../../assets/python_client.svg" not in content:
            content = re.sub(r'(# [^\n]+\n)', r'\1\n<img src="../../assets/python_client.svg" alt="Python Client" width="600"/>\n\n', content, count=1)
    elif client_name:
        # Add image under title if not present
        if "assets/" not in content:
            img_tag = f'\n<img src="../../assets/{client_name}_client.svg" alt="{client_name} Client" width="600"/>\n\n'
            content = re.sub(r'(# [^\n]+\n)', r'\1' + img_tag, content, count=1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

update_file("README.md", "hub")
update_file("README.es.md", "hub")
update_file("clients/python/README.md", "python")
update_file("clients/python/README.es.md", "python")
update_file("clients/javascript/README.md", "js")
update_file("clients/javascript/README.es.md", "js")
update_file("clients/rust/README.md", "rust")
update_file("clients/rust/README.es.md", "rust")
update_file("clients/go/README.md", "go")
update_file("clients/go/README.es.md", "go")
update_file("clients/cpp/README.md", "cpp")
update_file("clients/cpp/README.es.md", "cpp")
update_file("clients/csharp/NerveClient/README.md", "csharp")
update_file("clients/csharp/NerveClient/README.es.md", "csharp")

print("READMEs updated.")
