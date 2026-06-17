def _seed_category_and_template():
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    s = get_session()
    cat = create_category(s, "不動産部会")
    t = create_item_template(s, cat.id, "視察研修会参加費", 5000, "人", 0, "receipt", "")
    ids = (cat.id, t.id)
    s.close()
    return ids


def _select_category(dlg, cat_id):
    idx = next(i for i in range(dlg._category.count())
               if dlg._category.itemData(i) == cat_id)
    dlg._category.setCurrentIndex(idx)


def _select_template(dlg, tmpl_id):
    """既存の最後の行（_add_row で自動作成される1行目）にテンプレートを選択する。"""
    row = dlg._rows[-1]
    for i in range(row.name_combo.count()):
        if row.name_combo.itemData(i) == tmpl_id:
            row.name_combo.setCurrentIndex(i)
            break


def test_project_form_saves_title_as_name(qtbot, memory_db):
    cat_id, t_id = _seed_category_and_template()
    from app.ui.project_form import ProjectFormDialog
    dlg = ProjectFormDialog()
    qtbot.addWidget(dlg)
    _select_category(dlg, cat_id)
    dlg._title.setText("2026 視察研修会参加費")
    _select_template(dlg, t_id)
    dlg._save()

    from app.database.connection import get_session
    from app.services.project_service import get_projects
    s = get_session()
    names = [p.name for p in get_projects(s)]
    s.close()
    assert "2026 視察研修会参加費" in names


def test_project_form_requires_title(qtbot, memory_db, monkeypatch):
    cat_id, t_id = _seed_category_and_template()
    import app.ui.project_form as pf
    monkeypatch.setattr(pf.QMessageBox, "warning", lambda *a, **k: None)
    dlg = pf.ProjectFormDialog()
    qtbot.addWidget(dlg)
    _select_category(dlg, cat_id)
    _select_template(dlg, t_id)
    # 件名は空のまま
    dlg._save()

    from app.database.connection import get_session
    from app.services.project_service import get_projects
    s = get_session()
    count = len(get_projects(s))
    s.close()
    assert count == 0  # 件名未入力なので作成されない


def test_project_form_preview_warns_when_no_company(qtbot, memory_db, monkeypatch):
    """会社情報未登録(generate_preview=None)のとき警告を表示する。"""
    cat_id, t_id = _seed_category_and_template()
    import app.ui.project_form as pf
    import app.utils.pdf_helpers as ph
    monkeypatch.setattr(ph, "generate_preview", lambda lines, doc_type, session: None)
    warnings = []
    monkeypatch.setattr(pf.QMessageBox, "warning",
                        lambda *a, **k: warnings.append(a))
    dlg = pf.ProjectFormDialog()
    qtbot.addWidget(dlg)
    _select_category(dlg, cat_id)
    _select_template(dlg, t_id)
    dlg._preview()
    assert len(warnings) == 1  # プレビュー不可の警告が1回出る


def test_project_form_preview_uses_selected_templates(qtbot, memory_db, monkeypatch):
    cat_id, t_id = _seed_category_and_template()
    captured = {}
    import app.utils.pdf_helpers as ph
    monkeypatch.setattr(ph, "generate_preview",
                        lambda lines, doc_type, session: captured.update(
                            lines=lines, doc_type=doc_type) or "ok")
    from app.ui.project_form import ProjectFormDialog
    dlg = ProjectFormDialog()
    qtbot.addWidget(dlg)
    _select_category(dlg, cat_id)
    _select_template(dlg, t_id)
    # 種別＝領収書を選ぶ
    ridx = next(i for i in range(dlg._doc_type.count())
                if dlg._doc_type.itemData(i) == "receipt")
    dlg._doc_type.setCurrentIndex(ridx)
    dlg._preview()

    assert captured["doc_type"] == "receipt"
    assert len(captured["lines"]) == 1
    assert captured["lines"][0]["item_name"] == "視察研修会参加費"
    assert int(captured["lines"][0]["unit_price"]) == 5000
