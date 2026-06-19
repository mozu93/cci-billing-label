# app/database/models.py
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime,
    Numeric, Boolean, ForeignKey
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Supervisor(Base):
    __tablename__ = "supervisors"
    id       = Column(Integer, primary_key=True)
    name     = Column(String(100), nullable=False)
    email    = Column(String(200), default="")
    is_active = Column(Boolean, default=True)
    staff_id = Column(Integer, nullable=True)   # 職員から自動生成した場合の紐付け


class Staff(Base):
    __tablename__ = "staff"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    is_department_head = Column(Boolean, default=False)
    email = Column(String(200), nullable=True)
    password_hash = Column(String(200), nullable=True)
    supervisor_name  = Column(String(100), default="")   # 旧カラム（未使用）
    supervisor_email = Column(String(200), default="")   # 旧カラム（未使用）
    supervisor_id = Column(Integer, ForeignKey("supervisors.id"), nullable=True)
    supervisor = relationship("Supervisor")
    created_at = Column(DateTime, default=datetime.now)


class CompanySettings(Base):
    __tablename__ = "company_settings"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, default="")
    postal_code = Column(String(10), default="")
    address = Column(String(300), default="")
    phone = Column(String(50), default="")
    fax = Column(String(50), default="")
    email = Column(String(200), default="")
    invoice_reg_number = Column(String(20), default="")
    logo_path = Column(String(500), default="")
    print_seal = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    bank_accounts = relationship("BankAccount", back_populates="company",
                                 cascade="all, delete-orphan")
    seal_images = relationship("SealImage", back_populates="company",
                               cascade="all, delete-orphan")


class BankAccount(Base):
    __tablename__ = "bank_accounts"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("company_settings.id"), nullable=False)
    label = Column(String(100), nullable=False, default="")
    bank_name = Column(String(100), default="")
    bank_branch = Column(String(100), default="")
    bank_account_type = Column(String(20), default="普通")
    bank_account_number = Column(String(20), default="")
    bank_account_name = Column(String(100), default="")
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

    company = relationship("CompanySettings", back_populates="bank_accounts")


class SealImage(Base):
    __tablename__ = "seal_images"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("company_settings.id"), nullable=False)
    label = Column(String(100), nullable=False, default="")
    path = Column(String(500), default="")
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

    company = relationship("CompanySettings", back_populates="seal_images")


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

    item_templates = relationship("ItemTemplate", back_populates="category")


class ItemTemplate(Base):
    __tablename__ = "item_templates"
    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    name = Column(String(200), nullable=False)
    unit_price = Column(Numeric(15, 0), default=0)
    unit = Column(String(20), default="式")
    tax_rate = Column(Integer, default=10)
    doc_type = Column(String(20), default="both")
    description = Column(String(300), default="")
    notes = Column(Text, default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    category = relationship("Category", back_populates="item_templates")


class OperationLog(Base):
    __tablename__ = "operation_logs"
    id = Column(Integer, primary_key=True)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True)
    staff_name = Column(String(100), default="")
    action = Column(String(100), nullable=False)
    target_type = Column(String(50), default="")
    target_id = Column(Integer, nullable=True)
    detail = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    fiscal_year = Column(Integer, nullable=False)
    project_type = Column(String(20), default="list")
    status = Column(String(20), default="draft")
    issue_date = Column(Date, nullable=True)
    due_date = Column(Date, nullable=True)
    notes = Column(Text, default="")
    company_settings_id = Column(Integer, ForeignKey("company_settings.id"), nullable=True)
    bank_account_id     = Column(Integer, ForeignKey("bank_accounts.id"),    nullable=True)
    seal_image_id       = Column(Integer, ForeignKey("seal_images.id"),      nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    issuer       = relationship("CompanySettings", foreign_keys=[company_settings_id])
    bank_account = relationship("BankAccount",     foreign_keys=[bank_account_id])
    seal_image   = relationship("SealImage",       foreign_keys=[seal_image_id])


class ProjectTemplate(Base):
    __tablename__ = "project_templates"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    item_template_id = Column(Integer, ForeignKey("item_templates.id"), nullable=False)
    sort_order = Column(Integer, default=0)
    unit_price_override = Column(Numeric(15, 0), nullable=True)
    tax_rate_override = Column(Integer, nullable=True)
    default_quantity = Column(Integer, default=1)

    item_template = relationship("ItemTemplate")


class ProjectMember(Base):
    __tablename__ = "project_members"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    member_number = Column(String(50), default="")
    organization_name = Column(String(200), default="")
    organization_kana = Column(String(200), default="")
    representative_name = Column(String(100), default="")
    representative_kana = Column(String(100), default="")
    department = Column(String(100), default="")
    postal_code = Column(String(10), default="")
    address = Column(String(300), default="")
    address2 = Column(String(300), default="")
    phone = Column(String(50), default="")
    email = Column(String(200), default="")
    notes = Column(Text, default="")
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)


class Issuance(Base):
    __tablename__ = "issuances"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    project_member_id = Column(Integer, ForeignKey("project_members.id"), nullable=True)
    member_number = Column(String(50), default="")
    recipient_organization = Column(String(200), default="")
    recipient_kana = Column(String(200), default="")
    recipient_department = Column(String(100), default="")
    recipient_name = Column(String(100), default="")
    recipient_name_kana = Column(String(100), default="")
    recipient_phone = Column(String(50), default="")
    doc_type = Column(String(20), nullable=False)
    doc_number = Column(String(50), default="")
    status = Column(String(20), default="準備中")
    delivery_method = Column(String(20), default="窓口手渡し")
    amount = Column(Numeric(15, 0), default=0)
    pdf_path = Column(String(500), default="")
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True)
    staff_name = Column(String(100), default="")
    company_settings_id = Column(Integer, ForeignKey("company_settings.id"), nullable=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=True)
    seal_image_id = Column(Integer, ForeignKey("seal_images.id"), nullable=True)
    show_recipient_person = Column(Boolean, default=True)
    issued_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    lines = relationship("IssuanceLine", back_populates="issuance",
                         cascade="all, delete-orphan")


class IssuanceLine(Base):
    __tablename__ = "issuance_lines"
    id = Column(Integer, primary_key=True)
    issuance_id = Column(Integer, ForeignKey("issuances.id"), nullable=False)
    item_template_id = Column(Integer, ForeignKey("item_templates.id"), nullable=True)
    item_name = Column(String(300), nullable=False)
    quantity = Column(Numeric(10, 2), default=1)
    unit = Column(String(20), default="式")
    unit_price = Column(Numeric(15, 0), default=0)
    tax_rate = Column(Integer, default=10)
    line_total = Column(Numeric(15, 0), default=0)

    issuance = relationship("Issuance", back_populates="lines")


class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True)
    issuance_id = Column(Integer, ForeignKey("issuances.id"), nullable=False)
    payment_date = Column(Date, nullable=False)
    amount = Column(Numeric(15, 0), nullable=False)
    payment_method = Column(String(20), default="現金")
    notes = Column(String(200), default="")
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True)
    staff_name = Column(String(100), default="")
    created_at = Column(DateTime, default=datetime.now)


class Member(Base):
    __tablename__ = "members"
    id = Column(Integer, primary_key=True)
    member_number = Column(String(50), default="")
    organization_name = Column(String(200), default="")
    organization_kana = Column(String(200), default="")
    representative_name = Column(String(100), default="")
    representative_kana = Column(String(100), default="")
    department = Column(String(100), default="")
    phone = Column(String(50), default="")
    email = Column(String(200), default="")
    postal_code = Column(String(10), default="")
    address = Column(String(300), default="")
    address2 = Column(String(300), default="")
    created_at = Column(DateTime, default=datetime.now)
