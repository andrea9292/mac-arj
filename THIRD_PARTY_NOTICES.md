# 외부 구성요소와 라이선스 고지

## Mac ARJ 자체 코드

Copyright (C) 2026 Mac ARJ contributors.

프로젝트의 자체 소스와 문서는 **GNU Lesser General Public License 2.1 또는 이후 버전**(`LGPL-2.1-or-later`)으로 제공합니다. [LICENSE](LICENSE)에 수정하지 않은 LGPL 2.1 전문을 포함합니다. 이 파일은 라이선스 전문을 대체하지 않습니다.

## 7-Zip

- 프로젝트: [7-Zip](https://www.7-zip.org/)
- 저작권자: Igor Pavlov 및 해당 구성요소의 저작권자입니다. 정확한 연도·고지는 사용하는 배포본에서 확인합니다.
- 통합 방식: 별도로 설치한 `7zz` 실행 파일을 하위 프로세스로 호출합니다.
- 포함 여부: 이 저장소와 앱 번들에는 7-Zip 소스나 바이너리를 포함하지 않습니다. 7-Zip 라이브러리에 링크하지도 않습니다.
- 주 라이선스: **LGPL-2.1-or-later**입니다.
- 추가 조건: 사용하는 배포본·파일에 따라 BSD 2-Clause, BSD 3-Clause와 unRAR 제한 등이 일부 코드에 적용될 수 있습니다.
- 원문: [7-Zip license.txt](https://www.7-zip.org/license.txt)

Mac ARJ는 7-Zip의 주 라이선스와 같은 라이선스를 선택했지만, 7-Zip 전체의 복합 라이선스를 자체 코드에 그대로 붙이는 방식은 아닙니다. RAR 지원 코드를 복사하거나 포함하지 않으므로 unRAR 제한을 Mac ARJ 자체 코드의 추가 조건으로 선언하지 않습니다.

향후 7-Zip을 앱과 함께 배포하거나 소스를 가져오면, 실제 포함 파일의 라이선스·저작권·고지 보존·소스 제공 의무를 다시 검토해야 합니다. 현재 외부 설치 방식에 대한 설명을 번들 배포의 준수 근거로 사용하면 안 됩니다.

## 테스트 표본

`tests/generate_fixture.py`는 Python 표준 라이브러리로 저장 방식 ARJ 바이트를 직접 생성합니다. 사용자 파일이나 외부 압축 표본을 저장소에 포함하지 않습니다. 헤더 구조 확인에 참조한 공개 구현은 [7-Zip의 ArjHandler.cpp](https://github.com/ip7z/7zip/blob/main/CPP/7zip/Archive/ArjHandler.cpp)입니다. 테스트 생성기와 테스트 코드는 Mac ARJ 자체 소스의 라이선스를 따릅니다.

## 라이선스 원문 출처

[LICENSE](LICENSE)는 GNU의 [LGPL 2.1 공식 원문](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.txt)을 그대로 수록합니다. 전문 끝의 예시 고지에 있는 연도·저자 표기는 원문 일부이며, 이 프로젝트의 미작성 항목이 아닙니다. 이 프로젝트의 적용 범위와 저작권 고지는 위의 내용을 따릅니다.
