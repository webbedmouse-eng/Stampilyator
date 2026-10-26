# Сторонние компоненты и лицензии

«Штампилятор» распространяется под **GNU Affero General Public License
version 3 (AGPL-3.0-only)**. Полный текст — в файле [`LICENSE`](LICENSE).

Приложение собрано с использованием следующих компонентов. Полные тексты
лицензий находятся в каталоге [`licenses/`](licenses/).

| Компонент | Версия | Лицензия | Текст / источник |
|---|---|---|---|
| PyMuPDF | 1.27.2.3 | AGPL-3.0 | `licenses/AGPL-3.0.txt`; <https://pymupdf.readthedocs.io/> |
| MuPDF (в составе PyMuPDF) | 1.27.x | AGPL-3.0 | `licenses/AGPL-3.0.txt`; <https://mupdf.com/> |
| PySide6 / shiboken6 | 6.12.0 | LGPL-3.0 | `licenses/LGPL-3.0.txt`; <https://www.qt.io/licensing/open-source-lgpl-obligations> |
| Qt | 6.12 | LGPL-3.0 | `licenses/LGPL-3.0.txt`; <https://download.qt.io/official_releases/qt/6.12/> |
| Python | 3.14.4 | PSF-2.0 | `licenses/Python-3.14-PSF.txt`; <https://www.python.org/> |
| NumPy | 2.5.4 | BSD-3-Clause | `licenses/NumPy-BSD-3-Clause.txt`; <https://numpy.org/> |
| Pillow | 12.2.0 | HPND | `licenses/Pillow-HPND.txt`; <https://python-pillow.org/> |
| lxml | 6.1.0 | BSD-3-Clause | `licenses/lxml-BSD-3-Clause.txt`; <https://lxml.de/> |
| charset-normalizer | 3.4.7 | MIT | `licenses/charset-normalizer-MIT.txt`; <https://github.com/jawah/charset_normalizer> |
| FontTools | 4.63.0 | MIT | `licenses/fonttools-MIT.txt`; <https://fonttools.readthedocs.io/> |
| PyInstaller | 6.22.3 | GPL-2.0-or-later с исключением для загрузчика | `licenses/PyInstaller-GPL-2.0-with-exception.txt`; <https://pyinstaller.org/> |

## Исходный код зависимостей

- PyMuPDF 1.27.2.3: <https://pypi.org/project/PyMuPDF/1.27.2.3/#files>
- MuPDF: <https://github.com/ArtifexSoftware/mupdf>
- PySide6 6.12.0: <https://pypi.org/project/PySide6/6.12.0/#files>
- Qt 6.12: <https://download.qt.io/official_releases/qt/6.12/>
- Python 3.14.4: <https://www.python.org/downloads/release/python-3144/>

Если вы распространяете приложение, сохраняйте этот файл, каталог
`licenses/` и архив исходников рядом с EXE. Для PyMuPDF и Qt это также
означает, что получатель должен иметь возможность получить исходный код
соответствующих версий по указанным выше ссылкам.

## Примечание по LGPL и Qt

Qt/PySide6 используется как динамически подключаемая библиотека. Файлы Qt
находятся в папке `_internal`; пользователь может заменить их совместимой
версией. Текст LGPL-3.0 приложен. Исходники Qt доступны по ссылке выше.

## Примечание по PyMuPDF

PyMuPDF распространяется по AGPL-3.0 или по коммерческой лицензии Artifex.
В этой сборке используется AGPL-3.0. Исходный код приложения и инструкции
по сборке находятся в архиве `Штампилятор-1.3.2-source.zip` рядом с EXE.
