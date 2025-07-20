import os
import re

def sanitize_filename(name):
    # 파일 이름에서 사용할 수 없는 문자 제거
    return re.sub(r'[<>:"/\\|?*]', '', name).strip().replace(' ', '_')

for filename in os.listdir():
    if filename.endswith(".md"):
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # title: 이 포함된 줄 찾기
        for line in lines:
            if line.strip().startswith("title:"):
                title = line.strip().replace("title:", "").strip().strip('"').strip("'")
                new_name = sanitize_filename(title) + ".md"
                if filename != new_name:
                    try:
                        os.rename(filename, new_name)
                        print(f"✅ {filename} → {new_name}")
                    except Exception as e:
                        print(f"❌ {filename} 이름 변경 실패: {e}")
                break
