import sqlite3
from updater import parse_pension_html, _stores_from_html, _build_pension_rows

PENSION_HTML = '''
<html><body><table>
<tr><th>1등</th><td><span>3</span><span>6</span><span>4</span><span>4</span><span>5</span><span>1</span><span>3</span></td><td>월 700만원 X 20년</td></tr>
<tr><th>보너스</th><td><span>1</span><span>7</span><span>7</span><span>2</span><span>3</span><span>7</span></td></tr>
</table></body></html>
'''

STORE_HTML = '''
<table><tbody>
<tr><td>1등</td><td>행운복권방</td><td>서울특별시 강남구 테헤란로 1</td><td>02-1234-5678</td><td>자동</td></tr>
<tr><td>2등</td><td>복권마을</td><td>경기도 수원시 팔달구 효원로 2</td><td>031-222-3333</td><td></td></tr>
</tbody></table>
'''


def test_pension_parser():
    rows = parse_pension_html(PENSION_HTML, 328)
    assert len(rows) == 8
    one = next(r for r in rows if r['rank'] == 1)
    bonus = next(r for r in rows if r['rank'] == 21)
    assert one['rank_class'] == '3'
    assert one['rank_no'] == '644513'
    assert bonus['rank_no'] == '177237'
    assert next(r for r in rows if r['rank'] == 3)['rank_no'] == '44513'


def test_store_parser():
    rows = _stores_from_html(STORE_HTML, 1237)
    assert len(rows) == 2
    assert rows[0]['rank'] == 1
    assert rows[0]['name'] == '행운복권방'
    assert rows[0]['region'] == '서울'
    assert rows[1]['rank'] == 2
    assert rows[1]['region'] == '경기'


def test_builder_validation():
    rows = _build_pension_rows(329, 2, '123456', '654321', '2026-08-20')
    assert [r['rank'] for r in rows] == [1,2,3,4,5,6,7,21]
    assert rows[4]['rank_no'] == '456'


if __name__ == '__main__':
    test_pension_parser()
    test_store_parser()
    test_builder_validation()
    print('test_updater: ok')
