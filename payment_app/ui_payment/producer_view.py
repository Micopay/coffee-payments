"""
Producer Management Widget
Search, create, and view producer information
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QListWidget,
    QListWidgetItem, QMessageBox, QGroupBox,
    QFileDialog, QTextEdit
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap

from core.database import get_session, close_session
from core.models import Producer
from datetime import datetime, timezone
import shutil
import os


class ProducerManagementWidget(QWidget):
    """Widget for managing coffee producers"""
    
    producer_selected = Signal(Producer)
    
    def __init__(self):
        super().__init__()
        self.current_producer = None
        self.init_ui()
        self.load_producers()
    
    def init_ui(self):
        """Initialize the user interface"""
        layout = QHBoxLayout(self)
        layout.setSpacing(20)
        
        # Left side: Search and list
        left_panel = self.create_left_panel()
        layout.addWidget(left_panel, 1)
        
        # Right side: Producer details/form
        right_panel = self.create_right_panel()
        layout.addWidget(right_panel, 2)
    
    def create_left_panel(self) -> QGroupBox:
        """Create left panel with search and list"""
        group = QGroupBox("Productores")
        layout = QVBoxLayout()
        
        # Search
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Buscar productor...")
        self.search_input.textChanged.connect(self.filter_producers)
        search_layout.addWidget(self.search_input)
        
        layout.addLayout(search_layout)
        
        # Producer list
        self.producer_list = QListWidget()
        self.producer_list.itemClicked.connect(self.on_producer_selected)
        layout.addWidget(self.producer_list)
        
        # New producer button
        new_btn = QPushButton("➕ Nuevo Productor")
        new_btn.clicked.connect(self.show_new_producer_form)
        layout.addWidget(new_btn)
        
        group.setLayout(layout)
        return group
    
    def create_right_panel(self) -> QGroupBox:
        """Create right panel with producer details/form"""
        self.right_group = QGroupBox("Detalles del Productor")
        self.right_layout = QVBoxLayout()
        
        # Initial empty state
        empty_label = QLabel("Seleccione un productor o cree uno nuevo")
        empty_label.setAlignment(Qt.AlignCenter)
        empty_label.setStyleSheet("color: #A19F9D; font-size: 11pt;")
        self.right_layout.addWidget(empty_label)
        
        self.right_group.setLayout(self.right_layout)
        return self.right_group
    
    def load_producers(self):
        """Load all producers into the list"""
        try:
            session = get_session()
            producers = session.query(Producer).filter_by(is_active=True).order_by(Producer.name).all()
            
            self.producer_list.clear()
            for producer in producers:
                item = QListWidgetItem(f"☕ {producer.name}")
                item.setData(Qt.UserRole, producer.id)
                self.producer_list.addItem(item)
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al cargar productores:\n{str(e)}")
        finally:
            close_session()
    
    def filter_producers(self, text: str):
        """Filter producers by search text"""
        for i in range(self.producer_list.count()):
            item = self.producer_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())
    
    def on_producer_selected(self, item: QListWidgetItem):
        """Handle producer selection"""
        try:
            producer_id = item.data(Qt.UserRole)
            session = get_session()
            producer = session.query(Producer).filter_by(id=producer_id).first()
            
            if producer:
                self.current_producer = producer
                self.show_producer_details(producer)
                self.producer_selected.emit(producer)
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al cargar productor:\n{str(e)}")
        finally:
            close_session()
    
    def clear_layout(self, layout):
        """Recursively clear all widgets and sub-layouts from a layout"""
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                self.clear_layout(item.layout())

    def show_producer_details(self, producer: Producer):
        """Show producer details"""
        # Clear layout robustly
        self.clear_layout(self.right_layout)
        
        # Producer info
        info_layout = QFormLayout()
        
        name_label = QLabel(producer.name)
        name_label.setStyleSheet("font-size: 16pt; font-weight: 600;")
        info_layout.addRow("Nombre:", name_label)
        
        info_layout.addRow("Dirección XRPL:", QLabel(producer.xrpl_address))
        
        created_str = producer.created_at.strftime("%d/%m/%Y")
        info_layout.addRow("Registrado:", QLabel(created_str))
        
        if producer.contact_info:
            info_layout.addRow("Contacto:", QLabel(producer.contact_info))
        
        self.right_layout.addLayout(info_layout)
        
        # Image if available
        if producer.id_image_path and os.path.exists(producer.id_image_path):
            image_label = QLabel()
            pixmap = QPixmap(producer.id_image_path)
            scaled_pixmap = pixmap.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            image_label.setPixmap(scaled_pixmap)
            image_label.setAlignment(Qt.AlignCenter)
            self.right_layout.addWidget(image_label)
        
        # Historical aggregates
        from sqlalchemy import func
        from core.models import Payment, Delivery, PaymentStatus
        from core.utils import format_currency

        try:
            stats_session = get_session()

            # Count and sum payments (excluding FAILED)
            payment_stats = stats_session.query(
                func.count(Payment.id).label('count'),
                func.sum(Payment.amount_mxn).label('total_mxn'),
            ).filter(
                Payment.producer_id == producer.id,
                Payment.status != PaymentStatus.FAILED
            ).first()

            # Sum weight from deliveries
            weight_stats = stats_session.query(
                func.sum(Delivery.weight_kg).label('total_kg'),
            ).join(Payment).filter(
                Payment.producer_id == producer.id,
                Payment.status != PaymentStatus.FAILED
            ).first()

            # Last payment date
            last_payment = stats_session.query(Payment.timestamp).filter(
                Payment.producer_id == producer.id,
                Payment.status != PaymentStatus.FAILED
            ).order_by(Payment.timestamp.desc()).first()

            pay_count = payment_stats.count or 0
            total_mxn = float(payment_stats.total_mxn or 0)
            total_kg = float(weight_stats.total_kg or 0)
            last_date = last_payment.timestamp.strftime("%d/%m/%Y") if last_payment else "—"

            hist_group = QGroupBox("Historial de Entregas")
            hist_layout = QFormLayout()
            hist_layout.addRow("Total entregas:", QLabel(str(pay_count)))
            hist_layout.addRow("Total kg:", QLabel(f"{total_kg:.2f} kg"))
            hist_layout.addRow("Total pagado:", QLabel(format_currency(total_mxn, "MXN")))
            hist_layout.addRow("Último pago:", QLabel(last_date))
            hist_group.setLayout(hist_layout)
            self.right_layout.addWidget(hist_group)

        except Exception:
            pass
        finally:
            close_session()

        self.right_layout.addStretch()

        # Select button
        select_btn = QPushButton("✓ Seleccionar para Pago")
        select_btn.setProperty("class", "large")
        select_btn.clicked.connect(lambda: self.producer_selected.emit(producer))
        self.right_layout.addWidget(select_btn)
    
    def show_new_producer_form(self):
        """Show form to create new producer"""
        # Clear layout robustly
        self.clear_layout(self.right_layout)
        
        self.right_group.setTitle("Nuevo Productor")
        
        form_layout = QFormLayout()
        
        # Name
        self.new_name_input = QLineEdit()
        self.new_name_input.setPlaceholderText("Nombre completo del productor")
        form_layout.addRow("Nombre:*", self.new_name_input)
        
        # XRPL Address
        self.new_xrpl_input = QLineEdit()
        self.new_xrpl_input.setPlaceholderText("rXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
        form_layout.addRow("Dirección XRPL:*", self.new_xrpl_input)
        
        # Contact info
        self.new_contact_input = QTextEdit()
        self.new_contact_input.setPlaceholderText("Teléfono, email, etc.")
        self.new_contact_input.setMaximumHeight(80)
        form_layout.addRow("Contacto:", self.new_contact_input)
        
        # Image
        self.new_image_path = None
        self.image_btn = QPushButton("📷 Seleccionar Imagen de Identificación")
        self.image_btn.setProperty("class", "secondary")
        self.image_btn.clicked.connect(self.select_image)
        form_layout.addRow("Imagen:", self.image_btn)
        
        self.image_label = QLabel("No se ha seleccionado imagen")
        self.image_label.setStyleSheet("font-size: 9pt; color: #605E5C;")
        form_layout.addRow("", self.image_label)
        
        self.right_layout.addLayout(form_layout)
        
        self.right_layout.addStretch()
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setProperty("class", "secondary")
        cancel_btn.clicked.connect(self.cancel_new_producer)
        btn_layout.addWidget(cancel_btn)
        
        btn_layout.addStretch()
        
        save_btn = QPushButton("💾 Guardar Productor")
        save_btn.clicked.connect(self.save_new_producer)
        btn_layout.addWidget(save_btn)
        
        self.right_layout.addLayout(btn_layout)
    
    def select_image(self):
        """Select ID image"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar Imagen",
            "",
            "Images (*.png *.jpg *.jpeg)"
        )
        
        if file_path:
            self.new_image_path = file_path
            self.image_label.setText(f"✓ {os.path.basename(file_path)}")
    
    def save_new_producer(self):
        """Save new producer"""
        try:
            name = self.new_name_input.text().strip()
            xrpl = self.new_xrpl_input.text().strip()
            contact = self.new_contact_input.toPlainText().strip()
            
            if not name or not xrpl:
                QMessageBox.warning(
                    self,
                    "Campos Incompletos",
                    "Por favor, complete los campos obligatorios (*)."
                )
                return
            
            from core.xrpl_client import validate_xrpl_address
            if not validate_xrpl_address(xrpl):
                QMessageBox.warning(
                    self,
                    "Dirección Inválida",
                    "La dirección XRPL no es válida. Verifique el checksum."
                )
                return
            
            # Check if XRPL address already exists via Wallet
            session = get_session()
            from core.models import Wallet
            wallet = session.query(Wallet).filter_by(network="XRPL", address=xrpl, owner_type="producer").first()
            existing = session.query(Producer).get(wallet.owner_id) if wallet else None
            
            if existing:
                QMessageBox.warning(
                    self,
                    "Productor Duplicado",
                    f"Ya existe un productor con esta dirección XRPL:\n{existing.name}"
                )
                return
            
            # Copy image if provided
            image_path = None
            if self.new_image_path:
                # Create images directory
                images_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "producer_images")
                os.makedirs(images_dir, exist_ok=True)
                
                # Copy image
                ext = os.path.splitext(self.new_image_path)[1]
                image_filename = f"producer_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
                image_path = os.path.join(images_dir, image_filename)
                shutil.copy2(self.new_image_path, image_path)
            
            # Create producer
            new_producer = Producer(
                name=name,
                xrpl_address=xrpl,
                contact_info=contact if contact else None,
                id_image_path=image_path,
                created_at=datetime.now(timezone.utc),
                is_active=True
            )
            
            session.add(new_producer)
            session.commit()

            from core.audit import log_audit
            log_audit(session, None, "Productor creado",
                      f"Nombre: {name} | XRPL: {xrpl}")
            session.commit()

            QMessageBox.information(
                self,
                "Productor Creado",
                f"✓ Productor '{name}' creado exitosamente."
            )
            
            # Reload list and show new producer
            self.load_producers()
            self.right_group.setTitle("Detalles del Productor")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al guardar productor:\n{str(e)}")
        finally:
            close_session()
    
    def cancel_new_producer(self):
        """Cancel new producer creation"""
        self.right_group.setTitle("Detalles del Productor")
        self.clear_layout(self.right_layout)
        
        empty_label = QLabel("Seleccione un productor o cree uno nuevo")
        empty_label.setAlignment(Qt.AlignCenter)
        empty_label.setStyleSheet("color: #A19F9D; font-size: 11pt;")
        self.right_layout.addWidget(empty_label)
