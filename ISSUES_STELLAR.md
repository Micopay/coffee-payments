# Desglose en Issues — Multicadena XRPL + Stellar

Descomposición de `PLAN_STELLAR.md` en 20 issues independientes, listos para GrantFox / Drips.
Formato según `docs/DRIPS_TEAM_GUIDE.md` de `Micopay/micopay-protocol`: problema, razón, archivos en alcance, fuera de alcance, criterios de aceptación, pruebas y dependencias.

**Regla de oro del desglose:** dos issues nunca son dueñas del mismo archivo al mismo tiempo. La tabla de propiedad de archivos (al final) es la fuente de verdad para evitar conflictos de merge.

---

## Orden de ejecución

```
OLA 0 — arranque inmediato, 5 personas en paralelo, sin dependencias
  ├── XLM-01  Spike: pagos en Stellar Testnet
  ├── XLM-02  Spike: escrow con transacciones preautorizadas
  ├── XLM-03  Spike: firma remota con LOBSTR
  ├── XLM-04  Protocolo LedgerClient + shim de XRPLClient
  └── XLM-06  Modelo de datos multicadena  ← CAMINO CRÍTICO, empezar el día 1

OLA 1 — 6 en paralelo
  ├── XLM-05  StellarClient: pagos, saldo, activación      [01, 04]
  ├── XLM-07  ISO 20022 parametrizado por red              [04]
  ├── XLM-08  Alta de direcciones Stellar                  [06]
  ├── XLM-09  WalletSession y conexión perezosa            [04, 06]
  ├── XLM-14  Historial, detalle y recibo por red          [06]
  ├── XLM-15  Métricas de admin por red                    [06]
  └── XLM-18  Backend: endpoints de firma Stellar          [03]

OLA 2 — 4 en paralelo
  ├── XLM-10  Selector de red y pago directo               [05, 06, 07, 09]
  ├── XLM-11  Doble saldo en el dashboard                  [05, 09]
  ├── XLM-12  Escrow Stellar en StellarClient              [02, 05, 06]
  └── XLM-16  camt.053 por red                             [06, 07]

OLA 3
  └── XLM-13  escrow_view multicadena                      [09, 12]

OLA 4
  └── XLM-17  SignDialog genérico + cierre de Fase X5      [13]

OLA 5
  └── XLM-19  Cliente LOBSTR y cableado en la app          [10, 17, 18]

OLA 6
  └── XLM-20  Limpieza, tests finales y documentación      [todo]
```

**Camino crítico:** `XLM-01 → XLM-05 → XLM-12 → XLM-13 → XLM-17 → XLM-19 → XLM-20` (7 niveles).
**Cuello de botella:** `XLM-06` desbloquea 7 issues. Debe asignarse primero y a alguien con contexto de la base de datos.
**Hito de valor:** con `XLM-01, 04, 05, 06, 07, 09, 10, 11` la plataforma ya paga en ambas redes desde la misma pantalla.

---

## Contratos entre issues (acordar ANTES de empezar en paralelo)

Cuando dos issues corren a la vez y una consume la interfaz de la otra, la interfaz se define primero en un comentario del issue dueño y no se cambia sin avisar.

| # | Contrato | Dueño | Consumidores |
|---|---|---|---|
| C1 | Firma del `Protocol LedgerClient` y del enum `Network` | XLM-04 | 05, 07, 09, 12 |
| C2 | `WalletSession.signer_for(network)` | XLM-09 | 10, 11, 13, 19 |
| C3 | Firma de constructor de `PaymentFlowWidget` y `PaymentDashboard` | XLM-09 | 10, 11 |
| C4 | Esquema JSON de `EscrowDetail.chain_data` por red | XLM-06 | 12, 13 |
| C5 | Nombre del parámetro de red en `iso_generator` | XLM-07 | 16 |

---

## Etiquetas

Ya creadas en `Micopay/coffee-payments`. GrantFox exige que la etiqueta exista antes de publicar el issue.

| Etiqueta | Color | Uso |
|---|---|---|
| `complexity: low` | `#0e8a16` | Cambio acotado, pocas pruebas |
| `complexity: medium` | `#fbca04` | Pantalla, endpoint o módulo autocontenido |
| `complexity: high` | `#d93f0b` | Integración sustancial o máquina de estados |
| `backend` | `#1d76db` | `core/`, `backend/`, modelo de datos, ledger |
| `frontend` | `#5319e7` | PySide6: `payment_app`, `admin_app`, `shared_ui` |
| `research` | `#c5def5` | Spike o validación; el entregable es la conclusión |
| `stellar-multichain` | `#6f42c1` | Workstream completo (este documento) |
| `good first issue` | `#7057ff` | Ya existía |
| `documentation` | `#0075ca` | Ya existía |

Si los issues se atan a una campaña de GrantFox, esa campaña añade sus propias etiquetas (`GrantFox OSS`, `Maybe Rewarded`, la de campaña) al publicarse — no hay que crearlas a mano.

---
---

# OLA 0

## [XLM-01] Spike: pagos básicos en Stellar Testnet

**Complejidad:** medium · **Etiquetas:** `backend`, `research` · **Depende de:** nada

**Problema.** No hemos ejecutado una sola transacción de Stellar desde este proyecto. Antes de diseñar la capa de red necesitamos evidencia de cómo se comporta el SDK y dónde difiere de XRPL.

**Por qué importa.** Tres diferencias frente a XRPL pueden romper el diseño si se descubren tarde: una cuenta destino inexistente exige `CreateAccount` en vez de `Payment`, `MemoText` está limitado a 28 bytes (el UETR mide 36) y los montos usan 7 decimales. Este spike las confirma con transacciones reales.

**Alcance.** Crear `scripts/spike_stellar.py`, autocontenido, sin importar nada de la app, siguiendo el patrón de `scripts/spike_escrow.py`.

1. Crear dos cuentas de testnet con friendbot (`https://friendbot.stellar.org?addr=<G...>`); imprimir direcciones y saldos.
2. Pago de 10 XLM de A a B con `MemoHash` derivado de un UETR (16 bytes crudos del UUID rellenados a 32); verificar en Horizon e imprimir la URL de `stellar.expert`.
3. Pago a una cuenta **inexistente**: confirmar que falla con `op_no_destination`, y que `CreateAccount` con 1 XLM sí funciona.
4. Validación de direcciones con `StrKey.is_valid_ed25519_public_key`, incluyendo una dirección XRPL (debe rechazarla) y casos con checksum roto.

**Fuera de alcance.** Escrow (es XLM-02), cualquier cambio en `core/`, cualquier cosa de UI.

**Criterios de aceptación.**
- El script corre de punta a punta contra testnet e imprime hashes verificables.
- El encabezado del archivo documenta, en comentarios, la forma exacta del memo y el criterio para elegir entre `Payment` y `CreateAccount`.
- Si no hay red, el script sale limpiamente con un mensaje, igual que `spike_xaman.py`.

**Pruebas.** Ejecución manual documentada en el issue con los hashes de las transacciones de prueba.

---

## [XLM-02] Spike: escrow con transacciones preautorizadas

**Complejidad:** high · **Etiquetas:** `backend`, `research` · **Depende de:** nada

**Problema.** Stellar no tiene operación de escrow. El plan (decisión D4) propone una cuenta efímera con dos transacciones preautorizadas mutuamente excluyentes. Ese diseño hay que probarlo antes de construir nada encima.

**Por qué importa.** El invariante I3 del plan exige que los fondos bloqueados solo puedan terminar en el productor o de vuelta en el operador. Si el diseño tiene una fuga, este spike es el único lugar barato para descubrirla. Los *claimable balances* ya se descartaron porque sus predicados son solo temporales y dejarían al productor cobrar sin aprobación de calidad.

**Alcance.** Crear `scripts/spike_stellar_escrow.py` implementando el ciclo de D4:

```
1. CreateAccount(escrow, monto + 2.0 XLM)                    [firma: operador]
2. Construir con secuencia S+2, sin enviar:
   TX_LIBERAR   = [Payment(escrow→productor), AccountMerge(escrow→operador)]
   TX_REEMBOLSO = [AccountMerge(escrow→operador)]  con minTime = T
3. TX_SETUP (secuencia S+1)                                  [firma: llave efímera]
   [SetOptions(signer=preAuthTx(hash(TX_LIBERAR))),
    SetOptions(signer=preAuthTx(hash(TX_REEMBOLSO))),
    SetOptions(master_weight=0, thresholds 1/1/1)]
4. Descartar la llave efímera.
```

Probar: ciclo de liberación, ciclo de reembolso con ventana de 2 minutos, y las **pruebas negativas obligatorias**:
- `TX_REEMBOLSO` es rechazada antes de `minTime`.
- Ejecutada una, la otra queda inválida (comparten secuencia).
- Con la llave efímera descartada, nadie puede construir una transacción alternativa que saque los fondos.

**Fuera de alcance.** Integración con la app, persistencia, UI.

**Criterios de aceptación.**
- Los dos ciclos completos corren en testnet con hashes verificables.
- Las tres pruebas negativas fallan como se espera y el script lo imprime explícitamente.
- El script imprime el costo real en XLM de un ciclo completo.
- El encabezado documenta la secuencia exacta y la advertencia sobre la comisión: el hash de una transacción preautorizada incluye su `fee`, así que se fija holgada (10 000 stroops) y, si hiciera falta, se envuelve en un fee-bump.

**Pruebas.** Ejecución manual documentada con los hashes de ambos ciclos y la salida de las pruebas negativas.

---

## [XLM-03] Spike: firma remota con LOBSTR

**Complejidad:** high · **Etiquetas:** `research` · **Depende de:** nada

**Problema.** LOBSTR no expone un API de solicitudes de firma equivalente al de Xaman. Hay tres caminos posibles y ninguno está confirmado. No podemos diseñar la Fase de billetera dual sin saber cuál funciona.

**Por qué importa.** Este es el único riesgo del plan que puede terminar en "no se puede". Aislarlo en un spike permite que todo lo demás avance sin quedar bloqueado: si ningún camino funciona, Stellar se queda en modo seed con funcionalidad completa y se documenta la limitación.

**Alcance.** Crear `scripts/spike_lobstr.py` y probar, en este orden, hasta que uno funcione:

1. **SEP-7** — construir `web+stellar:tx?xdr=<b64url>&callback=url:<endpoint>&msg=...&network_passphrase=...`, renderizar el QR en consola, escanear con LOBSTR y comprobar si la app lo interpreta y si entrega el XDR firmado al callback. Levantar un receptor HTTP local o un túnel para recibirlo.
2. **WalletConnect v2** — LOBSTR lo documenta oficialmente, pero no existe cliente *dapp* en Python (`pyWalletConnect` es del lado billetera). Documentar el alcance real de un sidecar Node con `@walletconnect/sign-client`: qué haría falta y cuánto pesa.
3. **API de LOBSTR Vault** (`POST https://vault.lobstr.co/api/transactions/`, sin autenticación) — verificar si exige cuenta multifirma con el firmante del Vault y si opera solo en mainnet.

**Fuera de alcance.** Implementar el camino elegido (eso es XLM-18 y XLM-19). Aquí solo se produce evidencia.

**Criterios de aceptación.**
- **Un resultado negativo es un resultado válido.** El entregable es la conclusión, no el éxito.
- El encabezado del script documenta, para cada camino: funciona / no funciona / funciona con condiciones, con la evidencia observada.
- Recomendación explícita de cuál implementar en XLM-18/XLM-19, o de dejar Stellar en modo seed.
- Si SEP-7 funciona, dejar registrado el formato exacto del callback (método HTTP, content-type, nombre del campo).

**Pruebas.** Capturas o transcripción de la interacción con la app, en el comentario del issue.

---

## [XLM-04] Protocolo `LedgerClient` y shim de `XRPLClient`

**Complejidad:** medium · **Etiquetas:** `backend` · **Depende de:** nada · **Contrato C1**

**Problema.** `core/xrpl_client.py` es una clase concreta que toda la app importa directamente (15 archivos). No hay forma de introducir una segunda cadena sin una interfaz común.

**Por qué importa.** Es el cimiento de todo lo demás: XLM-05, 07, 09 y 12 construyen contra esta interfaz. Se hace por `typing.Protocol` y no por herencia justamente para no reescribir el cliente XRPL, que ya cumple casi toda la superficie.

**Alcance.**

```
core/ledger/
├── __init__.py     # get_ledger(network) -> LedgerClient  |  enum Network
├── base.py         # Protocol LedgerClient
└── xrpl.py         # XRPLClient movido tal cual
core/rates.py       # MOCK_EXCHANGE_RATES + conversiones, con XLM_MXN añadido
core/xrpl_client.py # queda como reexport: from core.ledger.xrpl import *
```

Interfaz mínima (**contrato C1**, no cambiar sin avisar a los consumidores):

```python
class LedgerClient(Protocol):
    network: str          # 'XRPL' | 'STELLAR'
    native_asset: str     # 'XRP'  | 'XLM'
    decimals: int         # 6      | 7

    def validate_address(self, address: str) -> bool: ...
    def account_exists(self, address: str) -> bool: ...
    def get_balance(self, address: str) -> dict: ...       # {'native': float, 'raw': str}
    def build_payment(self, source, destination, amount, memo_uetr) -> object: ...
    def submit_signed(self, signed) -> dict: ...           # {'hash','validated','result'}
    def verify_transaction(self, tx_hash: str) -> dict: ...
    def explorer_url(self, tx_hash: str) -> str: ...
```

Añadir a `XRPLClient` los métodos que falten (`account_exists`, `explorer_url` como alias de `get_testnet_explorer_url`).

**Fuera de alcance.** `StellarClient` (XLM-05). Los métodos de escrow del protocolo se definen en XLM-12, no aquí.

**Criterios de aceptación.**
- Los 15 archivos que importan `core.xrpl_client` siguen funcionando sin tocarse.
- `get_ledger("XRPL")` devuelve un `XRPLClient`; `get_ledger("STELLAR")` lanza `NotImplementedError` con mensaje claro hasta que exista XLM-05.
- `pytest tests/ -v` en verde sin modificar ningún test existente. **Esa es la prueba de que el shim funciona.**

**Pruebas.** Test nuevo: el shim reexporta los mismos símbolos; `get_ledger` devuelve la clase correcta; `XLM_MXN` existe en las tasas.

---

## [XLM-06] Modelo de datos multicadena

**Complejidad:** high · **Etiquetas:** `backend` · **Depende de:** nada · **Contrato C4**
**⚠ Camino crítico — desbloquea 7 issues. Asignar primero.**

**Problema.** `Producer.xrpl_address` es `NOT NULL UNIQUE`, `Payment` no sabe en qué red se liquidó y `EscrowDetail` tiene tres columnas específicas de XRPL. El esquema actual no admite una segunda cadena.

**Por qué importa.** Es la única fase que modifica datos existentes: el punto de no retorno del plan. También es lo que desbloquea a casi todo el mundo, así que cuanto antes aterrice, antes arranca el resto.

**Dato que define el diseño:** de las 57 referencias a `xrpl_address` en el código, **solo una es consulta SQL** (`producer_view.py:323`). Las otras 56 son lecturas de atributo, interceptables con `@property`. Por eso la tabla genérica cuesta casi lo mismo que añadir columnas.

**Alcance.**

`core/models.py`:
```python
class Wallet(Base):
    __tablename__ = "wallets"
    id         = Column(Integer, primary_key=True)
    owner_type = Column(String(20), nullable=False)    # 'producer' | 'user'
    owner_id   = Column(Integer,    nullable=False)
    network    = Column(String(20), nullable=False)    # 'XRPL' | 'STELLAR'
    address    = Column(String(100), nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("network", "address", name="uq_wallet_net_addr"),)
```

- `Producer` / `User`: `address_for(network)`, `set_address(network, address)` y `@property xrpl_address` de compatibilidad.
- `Payment`: `+ network` (no nulo, por defecto `'XRPL'`); `xrpl_tx_hash` → `tx_hash` con `@property` de compatibilidad.
- `EscrowDetail`: `+ network`, `+ chain_data` (texto JSON); se eliminan `offer_sequence`, `condition_hex`, `fulfillment_hex`.

Esquema de `chain_data` (**contrato C4**):
```json
XRPL    → {"offer_sequence": 42, "condition_hex": "A025...", "fulfillment_hex": "A022..."}
STELLAR → {"escrow_account": "G...", "release_xdr": "AAAA...", "refund_xdr": "AAAA...", "sequence": "..."}
```

`scripts/migrate_004_multichain.py`, idempotente y con respaldo previo en `data/backups/` como los migradores existentes:
1. `CREATE TABLE wallets`.
2. Copiar `producers.xrpl_address` y `users.xrpl_address` con `network='XRPL'`, `is_default=1`.
3. `payments`: renombrar la columna de hash y añadir `network` relleno con `'XRPL'`.
4. `escrow_details`: añadir `network` y `chain_data`, volcar las tres columnas XRPL a JSON y eliminarlas. `DROP COLUMN` existe desde SQLite 3.35; si `sqlite3.sqlite_version` es menor, reconstruir la tabla.
5. **Dejar** `producers.xrpl_address` y `users.xrpl_address` en la tabla, sin uso. Se eliminan en XLM-20 para tener vuelta atrás durante el desarrollo.

`payment_app/ui_payment/producer_view.py:323`: cambiar `filter_by(xrpl_address=xrpl)` por una consulta sobre `Wallet` por `(network, address)`. Es el único cambio de este tipo en todo el proyecto.

**Fuera de alcance.** Cualquier UI de alta de direcciones (XLM-08). Cualquier uso de la red en el flujo de pago (XLM-10).

**Criterios de aceptación.**
- La migración corre sobre una copia de la base de datos real y es idempotente (ejecutarla dos veces no rompe nada).
- Un productor solo-Stellar es válido.
- **Los 8 usos de `xrpl_address` en `tests/test_core.py` pasan sin modificarse.** Esa es la prueba de que el shim funciona.
- `pytest tests/ -v` en verde.

**Pruebas.** Tests nuevos: el shim devuelve la misma dirección que antes de migrar; unicidad de `(network, address)`; `chain_data` sobrevive el viaje de ida y vuelta a JSON; migración idempotente.

---
---

# OLA 1

## [XLM-05] `StellarClient`: pagos, saldo, activación

**Complejidad:** high · **Etiquetas:** `backend` · **Depende de:** XLM-01, XLM-04

**Problema.** No existe implementación de la cadena Stellar. Con el protocolo definido y el spike hecho, toca escribir el cliente real.

**Por qué importa.** Es la pieza que convierte el trabajo de diseño en capacidad: sin esto no hay pago posible en Stellar.

**Alcance.** Crear `core/ledger/stellar.py` implementando `LedgerClient` (contrato C1), trasladando lo aprendido en XLM-01:
- Horizon testnet (`https://horizon-testnet.stellar.org`), `Network.TESTNET_NETWORK_PASSPHRASE`.
- Montos como `Decimal` de 7 decimales; `base_fee` de 100 stroops por operación.
- `MemoHash` con los 16 bytes crudos del UETR rellenados a 32.
- `account_exists()` y elección automática entre `Payment` y `CreateAccount`.
- `explorer_url()` apuntando a `stellar.expert/explorer/testnet`.
- Registrar `stellar-sdk>=15.0.0` en `requirements.txt`.

**Fuera de alcance.** Escrow (XLM-12). Firma remota (XLM-19). Cualquier UI.

**Criterios de aceptación.**
- `get_ledger("STELLAR")` devuelve un `StellarClient` funcional.
- Una dirección XRPL es rechazada por `validate_address`, y viceversa en el cliente XRPL.
- Pagar a una cuenta inexistente usa `CreateAccount` automáticamente y no falla.
- `pytest tests/ -v` en verde.

**Pruebas.** Unitarias con Horizon mockeado: construcción del memo, selección de operación según existencia de cuenta, conversión de montos, validación cruzada de direcciones. Una prueba manual en testnet documentada en el issue.

---

## [XLM-07] ISO 20022 parametrizado por red

**Complejidad:** medium · **Etiquetas:** `backend` · **Depende de:** XLM-04 · **Contrato C5**

**Problema.** `core/iso_generator.py` tiene `"XRPL"` fijo como `ClrSysMmbId` (líneas 139 y 158) y emite `<XRPLTxHash>` en los datos suplementarios. Un pago de Stellar generaría mensajes que mienten sobre la red de liquidación.

**Por qué importa.** La mensajería ISO 20022 es el corazón educativo del proyecto: que el mismo `pacs.008` sirva a dos rieles distintos es precisamente lo que se quiere demostrar. Si la red está incrustada, la demostración no se sostiene.

**Alcance.** En `core/iso_generator.py`:
- `ClrSysMmbId` toma `"XRPL"` o `"STELLAR"` según el pago.
- El elemento de hash pasa a `<LedgerTxHash Network="STELLAR">`. **Para XRPL se conserva `<XRPLTxHash>`** de modo que los mensajes nuevos sigan siendo byte a byte comparables con los ya almacenados.
- `generate_pacs002` recibe `result_code` genérico (`xrpl_result_code` queda como alias en desuso, sin romper llamadas existentes) y mapea también los códigos de Stellar: `tx_success` → ACSC; cualquier `tx_*` / `op_*` de error → RJCT con el código en `StsRsnInf`.

**Fuera de alcance.** `camt.053` por red (XLM-16). Cambios en quién llama al generador (XLM-10).

**Criterios de aceptación.**
- Un `pacs.008` de XRPL generado tras el cambio es idéntico al generado antes.
- Un `pacs.008` de Stellar declara `STELLAR` y `<LedgerTxHash Network="STELLAR">`.
- Los espacios de nombres siguen validando.
- `pytest tests/ -v` en verde sin tocar los tests ISO existentes.

**Pruebas.** Comparación literal del XML de XRPL antes y después; casos nuevos para Stellar en `pacs.008`, `pacs.002` (ACSC y RJCT) y `camt.054`.

---

## [XLM-08] Alta de direcciones Stellar

**Complejidad:** medium · **Etiquetas:** `frontend`, `good first issue` · **Depende de:** XLM-06

**Problema.** Las pantallas de alta de productores y de operadores solo aceptan direcciones de XRPL, y bloquean el botón de guardar si la dirección no es válida en esa red.

**Por qué importa.** Sin direcciones de Stellar registradas, nada del resto del trabajo es utilizable por la cooperativa.

**Alcance.**
- `payment_app/ui_payment/producer_view.py`: segundo campo de dirección (Stellar) con validación por `StrKey`; indicador de "cuenta no activada" cuando la cuenta no existe en el ledger; al menos una dirección obligatoria — ya no específicamente la de XRPL. Mostrar ambas direcciones en la ficha del productor.
- `admin_app/ui_admin/user_management.py`: campo de dirección Stellar del operador, con la misma validación.
- `core/utils.py`: `generate_user_id()` **sigue derivándose de la dirección XRPL** — los IDs ya emitidos no pueden cambiar. Para un operador solo-Stellar, generar desde su dirección Stellar. Documentar la regla en el docstring.

**Fuera de alcance.** Pagar en Stellar (XLM-10). Migración de datos (ya está en XLM-06).

**Criterios de aceptación.**
- Se puede dar de alta un productor con una sola red, con la otra, o con ambas.
- Una dirección de XRPL pegada en el campo de Stellar es rechazada con un mensaje claro, y viceversa.
- Los duplicados se detectan por `(red, dirección)`, no globalmente.
- Los productores existentes siguen visibles y editables.

**Pruebas.** Validación cruzada de direcciones; alta con una y con ambas redes; rechazo de duplicados por red.

---

## [XLM-09] `WalletSession` y conexión perezosa

**Complejidad:** high · **Etiquetas:** `frontend` · **Depende de:** XLM-04, XLM-06 · **Contratos C2, C3**

**Problema.** `AuthFlowDialog` devuelve `xrpl_seed` **o** `xaman_client` sueltos, y `main_payment.py:45` exige uno de los dos. Con dos redes hace falta una credencial por red, y pedir ambas al iniciar sesión obligaría a conectar dos billeteras aunque solo se vaya a usar una.

**Por qué importa.** Es lo que hace tolerable la interfaz dual. Sin conexión perezosa, la fricción del login mata la propuesta.

**Alcance.**
- Nuevo `core/wallet_session.py` con `WalletSession`: contenedor de firmantes indexado por red.
- **Contrato C2:** `signer_for(network)` devuelve el firmante de esa red y, si no existe, dispara el flujo de conexión y lo memoriza. Devuelve `None` si el operador cancela.
- `payment_app/ui_payment/auth_flow.py`: el paso 3 conecta **una** billetera (la red elegida) y construye el `WalletSession`.
- `payment_app/main_payment.py`: pasar el `WalletSession` al dashboard en lugar de `xrpl_seed` / `xaman_client`.
- **Contrato C3:** fijar en este issue la firma de constructor de `PaymentFlowWidget` y `PaymentDashboard`, porque XLM-10 y XLM-11 construyen contra ella en paralelo. Publicarla en un comentario del issue antes de que ellos empiecen.
- Al cerrar sesión se limpian todos los firmantes, igual que hoy se limpia el seed.

**Fuera de alcance.** El selector de red en el flujo de pago (XLM-10). LOBSTR (XLM-19) — aquí solo se deja el hueco.

**Criterios de aceptación.**
- Iniciar sesión conectando solo XRPL funciona igual que hoy.
- La primera vez que se pide un firmante de Stellar, se solicita la credencial; la segunda vez ya no.
- Cancelar la conexión de la segunda red deja la sesión utilizable en la primera.
- Ninguna credencial sobrevive al cierre de sesión ni al cierre de ventana.

**Pruebas.** Unitarias de `WalletSession` con firmantes falsos: memorización, cancelación, limpieza.

---

## [XLM-14] Historial, detalle y recibo por red

**Complejidad:** medium · **Etiquetas:** `frontend` · **Depende de:** XLM-06

**Problema.** El historial no distingue redes y todos los enlaces apuntan al explorador de XRPL. Un pago de Stellar aparecería con un enlace roto.

**Por qué importa.** La trazabilidad es la promesa central hacia el productor: "tu pago está en la cadena y aquí está la prueba". Un enlace equivocado la rompe.

**Alcance.**
- `payment_app/ui_payment/history_view.py`: columna **Red** con icono, filtro por red junto al de estado, enlace al explorador correcto.
- `payment_app/ui_payment/payment_detail_dialog.py`: mostrar la red y usar la URL correspondiente.
- `core/receipt.py`: la red aparece en el PDF y el enlace apunta al explorador correcto.

**Fuera de alcance.** Métricas (XLM-15). Cierre de día (XLM-16).

**Criterios de aceptación.**
- Un historial con pagos de ambas redes se ve correcto y cada enlace abre el explorador que toca.
- El filtro por red funciona combinado con el de estado.
- Los pagos anteriores a la migración se muestran como XRPL.
- El PDF del recibo declara la red.

**Pruebas.** Con base de datos sembrada con pagos de ambas redes: filtros, URLs generadas, contenido del recibo.

---

## [XLM-15] Métricas de admin por red

**Complejidad:** low · **Etiquetas:** `frontend`, `good first issue` · **Depende de:** XLM-06

**Problema.** `metrics_view.py` agrega totales sin distinguir la cadena de liquidación.

**Por qué importa.** La cooperativa necesita saber cuánto se movió por cada riel para decidir dónde concentrar la operación.

**Alcance.** En `admin_app/ui_admin/metrics_view.py`: desglose por red además del total, y la gráfica de barras existente con una serie por red. La forma de la vista no cambia.

**Fuera de alcance.** Cualquier otro archivo. Este issue es deliberadamente pequeño y aislado — buena primera contribución.

**Criterios de aceptación.**
- Los KPIs muestran total y desglose por red.
- La gráfica dibuja una serie por red y sigue leyéndose bien con una sola red presente.
- Un mes sin pagos de Stellar se ve igual que hoy.

**Pruebas.** Con datos sembrados de ambas redes: totales por red, y el caso de una sola red.

---

## [XLM-18] Backend: endpoints de firma para Stellar

**Complejidad:** high · **Etiquetas:** `backend` · **Depende de:** XLM-03

**Problema.** El backend solo sabe crear solicitudes de firma de Xaman. Para LOBSTR hace falta el equivalente en Stellar.

**Por qué importa.** Es la mitad servidor de la billetera dual, y es independiente de todo el trabajo de escritorio: puede avanzar en paralelo sin tocar un solo archivo de la app.

**Alcance.** Depende del resultado de XLM-03. Si SEP-7 resultó viable:
- `backend/stellar_service.py`: construcción de la URI `web+stellar:` y del QR.
- `backend/app.py`: `POST /stellar/sign-requests` (guarda el XDR sin firmar, devuelve `{id, uri, qr}`), `POST /stellar/callback/{id}` (**público**, recibe el XDR firmado de LOBSTR) y `GET /stellar/sign-requests/{id}` (polling autenticado, **mismo contrato de respuesta que el de Xaman**: `{resolved, signed, cancelled, expired, txid, account}`).
- `backend/models.py`: persistencia de la solicitud y su XDR firmado; reutilizar el patrón de `SignRequestLog`.
- Reutilizar `require_device` para los endpoints autenticados. El callback es público por necesidad: validarlo por identificador no adivinable y expiración corta.

Si XLM-03 concluyó que SEP-7 no funciona, este issue cambia de alcance según su recomendación, o se cierra como no aplicable.

**Fuera de alcance.** Cliente de escritorio y cableado (XLM-19). Enviar la transacción a Horizon — eso lo hace el escritorio.

**Criterios de aceptación.**
- El contrato de respuesta del polling es idéntico al de Xaman, para que el diálogo genérico de XLM-17 no tenga que ramificar.
- El callback rechaza identificadores desconocidos o expirados.
- Ninguna llave privada pasa por el backend (invariante I1).
- `backend/README.md` documenta los endpoints nuevos.

**Pruebas.** Tests del backend con el servicio mockeado: creación, callback correcto, callback con identificador inválido, expiración.

---
---

# OLA 2

## [XLM-10] Selector de red y pago directo en Stellar

**Complejidad:** high · **Etiquetas:** `frontend` · **Depende de:** XLM-05, XLM-06, XLM-07, XLM-09

**Problema.** `payment_flow.py` está cableado a XRPL de principio a fin: el cliente, los tokens, el memo, el explorador y los mensajes ISO.

**Por qué importa.** Es **el hito de valor del plan**: cuando este issue cierra, la plataforma ya es multicadena de verdad.

**Alcance.** En `payment_app/ui_payment/payment_flow.py`:
- Selector de red (`QRadioButton` XRPL / Stellar) sobre el selector de token.
- El combo de tokens se filtra por red: XRP / USDC / RLUSD / MXN frente a XLM / USDC / MXN.
- La red se deshabilita, con tooltip explicativo, si el productor no tiene dirección en ella.
- `_do_payment` y `_persist_payment` dejan de usar `self.xrpl_client` y usan `get_ledger(network)`; el firmante sale de `WalletSession.signer_for(network)` (contrato C2).
- `Payment.network` se persiste en cada pago.
- Los mensajes ISO se generan con la red correcta (XLM-07) y la activación de cuenta se resuelve según XLM-05.

**Fuera de alcance.** Escrow en Stellar — el modo escrow sigue deshabilitado para Stellar hasta XLM-13, con tooltip que lo explique. Saldos del encabezado (XLM-11).

**Criterios de aceptación.**
- Un pago real en Stellar Testnet desde la app, con `pacs.008` y `camt.054` generados y hash verificable en stellar.expert.
- **Un pago XRPL en la misma sesión se comporta exactamente igual que antes** — sin regresión.
- Elegir un productor sin dirección en la red seleccionada no permite pagar y explica por qué.
- Pagar a una cuenta de Stellar no activada funciona.

**Pruebas.** Unitarias del filtrado de tokens y del despacho por red; prueba manual en testnet documentada con ambos hashes.

---

## [XLM-11] Doble saldo en el dashboard

**Complejidad:** medium · **Etiquetas:** `frontend`, `good first issue` · **Depende de:** XLM-05, XLM-09 · **Contrato C3**

**Problema.** El encabezado muestra un solo saldo de XRP y un solo indicador de conexión.

**Por qué importa.** El operador necesita ver de un vistazo si tiene fondos en la red en la que va a pagar. Sin esto, se entera del saldo insuficiente a mitad del cobro, frente al productor.

**Alcance.** En `payment_app/ui_payment/dashboard.py`: dos saldos en el encabezado, cada uno en su propio `FunctionWorker` (el patrón ya existe en `refresh_balance`), con indicador de conexión independiente por red. Si una red está caída, la otra sigue mostrándose.

**Fuera de alcance.** El flujo de pago (XLM-10). Construir contra la firma de constructor fijada en XLM-09 (contrato C3) para no chocar.

**Criterios de aceptación.**
- Ambos saldos se cargan en paralelo sin congelar la interfaz.
- Una red sin conexión muestra su propio estado y no afecta a la otra.
- Un operador con billetera en una sola red ve el otro saldo como "no conectado", no como error.

**Pruebas.** Unitarias con clientes falsos: éxito en ambas, fallo en una, fallo en las dos.

---

## [XLM-12] Escrow de Stellar en `StellarClient`

**Complejidad:** high · **Etiquetas:** `backend` · **Depende de:** XLM-02, XLM-05, XLM-06 · **Contrato C4**

**Problema.** El escrow contra calidad solo existe en XRPL. Es la funcionalidad más distintiva de la plataforma y no tiene equivalente en Stellar.

**Por qué importa.** Sin escrow, Stellar es un riel de segunda dentro de la propia plataforma. El invariante I3 exige además que sea igual de restrictivo que el de XRPL.

**Alcance.** Llevar a `core/ledger/stellar.py` el diseño validado en XLM-02, con la misma firma que los métodos de `XRPLClient`:
- `create_escrow(...)` → `CreateAccount` + `TX_SETUP`, devolviendo en el diccionario los datos de `chain_data` (contrato C4): `escrow_account`, `release_xdr`, `refund_xdr`, `sequence`.
- `finish_escrow(...)` → enviar `TX_LIBERAR`.
- `cancel_escrow(...)` → enviar `TX_REEMBOLSO`.
- Extender el `Protocol` de XLM-04 con los tres métodos de escrow.
- La comisión de las transacciones preautorizadas se fija holgada (10 000 stroops) porque el hash la incluye; documentar el fee-bump como salida de emergencia.

**Fuera de alcance.** Cualquier UI (XLM-13). Firma remota (XLM-19).

**Criterios de aceptación.**
- Las pruebas negativas de XLM-02 se reproducen como tests automatizados donde sea posible.
- `chain_data` se serializa exactamente según el contrato C4.
- El ciclo completo corre en testnet por ambos desenlaces.
- Los métodos de escrow de XRPL siguen intactos.

**Pruebas.** Unitarias con Horizon mockeado para la construcción de las transacciones y la asignación de secuencias; prueba manual en testnet de ambos ciclos, documentada con hashes.

---

## [XLM-16] `camt.053` por red

**Complejidad:** medium · **Etiquetas:** `backend` · **Depende de:** XLM-06, XLM-07 · **Contrato C5**

**Problema.** El cierre de día genera un único `camt.053` que mezclaría pagos de ambas cadenas en un mismo estado de cuenta.

**Por qué importa.** Un `camt.053` declara una cuenta y una divisa de liquidación. Mezclar dos redes en un mismo documento lo vuelve inválido como estado de cuenta.

**Alcance.**
- `admin_app/ui_admin/audit_view.py`: el cierre de día genera **un estado de cuenta por red**, con sufijo de red en el nombre del archivo.
- `core/iso_generator.py`: `generate_camt053` recibe la red y la usa en los campos correspondientes, respetando el contrato C5 fijado en XLM-07.

**Fuera de alcance.** El resto del log de auditoría. Métricas (XLM-15).

**Criterios de aceptación.**
- Un período con pagos de ambas redes produce dos archivos, cada uno con solo sus movimientos.
- Un período con una sola red produce un archivo, igual que hoy.
- Los saldos de apertura y cierre cuadran por red.

**Pruebas.** Con datos sembrados de ambas redes: dos archivos correctos, y el caso de una sola red sin regresión.

---
---

# OLA 3

## [XLM-13] `escrow_view` multicadena

**Complejidad:** high · **Etiquetas:** `frontend` · **Depende de:** XLM-09, XLM-12 · **Contrato C4**

**Problema.** `escrow_view.py` asume XRPL en todo: los campos que lee, las llamadas que hace y la regla de tiempos que aplica.

**Por qué importa.** Es la pantalla donde la cooperativa decide si un productor cobra. Tiene que ser inequívoca con dos cadenas en la misma tabla.

**Alcance.** En `payment_app/ui_payment/escrow_view.py`:
- Columna **Red** en la tabla.
- Los botones Aprobar / Rechazar / Reembolsar despachan por red según la fila seleccionada.
- Leer `chain_data` según el contrato C4 en vez de las columnas eliminadas.
- `_update_buttons` ya depende de `cancel_after`, que es común a ambas cadenas: mantener esa lógica.
- **Regla de tiempos:** en Stellar sí sería posible liberar después del vencimiento mientras nadie haya enviado `TX_REEMBOLSO`. Para no dar al operador dos reglas distintas, la interfaz mantiene el comportamiento de XRPL (liberar solo antes del vencimiento). Documentar la diferencia en el docstring del módulo.
- El `pacs.002` ACSC transporta el XDR de liberación en el mismo lugar donde hoy va el fulfillment; `generate_pacs002(..., escrow_fulfillment=...)` pasa a aceptar cualquiera de los dos y etiquetar cuál es.

**Fuera de alcance.** Firmar escrows con billetera remota — sigue siendo modo seed hasta XLM-17 y XLM-19.

**Criterios de aceptación.**
- Ciclo completo en testnet por ambas redes: crear → aprobar → liberar, y crear → rechazar → esperar → reembolsar.
- Una tabla con escrows de ambas redes habilita los botones correctos en cada fila.
- Los escrows XRPL existentes siguen funcionando tras la migración.

**Pruebas.** Unitarias de la lógica de habilitación por red y estado; pruebas manuales de ambos ciclos en testnet, documentadas con hashes.

---
---

# OLA 4

## [XLM-17] `SignDialog` genérico y cierre de la Fase X5

**Complejidad:** high · **Etiquetas:** `frontend` · **Depende de:** XLM-13

**Problema.** `xaman_sign_dialog.py` es casi genérico — el QR, el polling, el timeout y `resolve_status()` no saben de XRPL — pero está atado a `XamanClient` y a `txjson`. Además, la Fase X5 de `PLAN_XAMAN.md` sigue abierta: `escrow_view.py:98` deshabilita los botones cuando no hay seed, así que **hoy no se puede gestionar un escrow con Xaman**.

**Por qué importa.** Las dos cosas necesitan exactamente la misma generalización. Hacerlas por separado sería hacer el trabajo dos veces.

**Alcance.**
- Mover el diálogo a `shared_ui/sign_dialog.py`, parametrizando el cliente de firma y el texto. `resolve_status()` se conserva como función pura y sus tests no cambian.
- `payment_app/ui_payment/xaman_sign_dialog.py` queda como shim que reexporta, para no romper llamadas existentes.
- **Cerrar la Fase X5:** habilitar la gestión de escrow XRPL con Xaman en `escrow_view.py`. `EscrowFinish` y `EscrowCancel` se construyen como `txjson` y se firman con el diálogo. El `offer_sequence` se obtiene consultando la transacción validada, según la decisión D6 de `PLAN_XAMAN.md`.

**Fuera de alcance.** LOBSTR (XLM-19). El diálogo debe quedar listo para recibirlo, no cableado a él.

**Criterios de aceptación.**
- Un pago con Xaman se comporta exactamente igual que antes.
- **Un escrow XRPL completo, firmado con Xaman de punta a punta, en testnet** — crear, aprobar y liberar. Esto cierra X5.
- El aviso de "escrow con Xaman en próxima versión" de `escrow_view.py:99` desaparece.
- Los tests de `resolve_status` pasan sin modificarse.

**Pruebas.** Los tests existentes del diálogo siguen verdes; prueba manual del ciclo de escrow con Xaman documentada con hashes.

---
---

# OLA 5

## [XLM-19] Cliente LOBSTR y cableado en la app

**Complejidad:** high · **Etiquetas:** `frontend`, `backend` · **Depende de:** XLM-10, XLM-17, XLM-18

**Problema.** Con el backend listo (XLM-18) y el diálogo genérico (XLM-17), falta la mitad de escritorio: el cliente HTTP, los ajustes y el cableado en los flujos.

**Por qué importa.** Es lo que completa la billetera dual: firmar en Stellar desde el teléfono, sin que la llave toque el software.

**Alcance.**
- `core/lobstr_client.py`: réplica de `core/xaman_client.py` contra los endpoints de XLM-18, incluyendo `from_config()`.
- `payment_app/ui_payment/settings_dialog.py`: sección de LOBSTR junto a la de Xaman, con las mismas claves cifradas en `AppConfig` y su propio "probar conexión".
- Cableado en `auth_flow.py` (registrar el firmante de Stellar en el `WalletSession`), `payment_flow.py` y `escrow_view.py`.

Si XLM-03 concluyó que ningún camino de LOBSTR es viable, este issue se cierra documentando la limitación en `README.md` y Stellar se queda en modo seed. **No es un bloqueo del proyecto**: XLM-10 y XLM-13 ya entregaron la funcionalidad completa.

**Fuera de alcance.** Notificaciones push (LOBSTR no ofrece el equivalente del `user_token` de Xaman).

**Criterios de aceptación.**
- Pago en Stellar firmado desde el teléfono, sin seed en la app.
- Escrow en Stellar firmado desde el teléfono, ciclo completo.
- Ninguna llave privada llega al backend (invariante I1).
- El modo seed sigue funcionando como alternativa.

**Pruebas.** Unitarias del cliente con backend mockeado; pruebas manuales de pago y escrow documentadas con hashes.

---
---

# OLA 6

## [XLM-20] Limpieza, tests finales y documentación

**Complejidad:** medium · **Etiquetas:** `backend`, `documentation` · **Depende de:** todos los anteriores

**Problema.** Tres residuos del trabajo multicadena: columnas muertas de la migración, documentación que sigue describiendo una plataforma mono-cadena, y el nombre de producto **"Coffee XRPL Platform"** incrustado en ~25 lugares — varios de ellos visibles para el usuario final.

**Por qué importa.** El README es la cara del proyecto: hoy dice "construida sobre el XRP Ledger" y describe una realidad que ya no es la que hay. Y el nombre de producto es peor que un detalle cosmético: aparece en el PDF del recibo que se le entrega al productor y en la instrucción que el operador lee en su teléfono al firmar. Un pago liquidado en Stellar que se anuncia como "XRPL Platform" es información incorrecta frente al usuario.

**Por qué va al final y no antes.** El renombrado toca archivos de los que son dueños casi todos los demás issues (`auth_flow.py` es de XLM-09, `dashboard.py` de XLM-11, `receipt.py` de XLM-14). Hacerlo antes generaría conflictos de merge con todo lo que esté en vuelo. Aquí ya no hay nadie trabajando en esos archivos.

**Alcance.**

*1. Limpieza de datos*
- `scripts/migrate_005_drop_legacy_address.py`: eliminar `producers.xrpl_address` y `users.xrpl_address`, que XLM-06 dejó a propósito como red de seguridad.

*2. Nombre de producto: `Coffee XRPL Platform` → `Coffee Payments`*

Reemplazo mecánico de la cadena. **Visible para el usuario** (prioridad):

| Archivo | Qué ve el usuario |
|---|---|
| `payment_app/ui_payment/auth_flow.py:513` | La instrucción que aparece en el teléfono al firmar con Xaman |
| `core/receipt.py:46,72` | El PDF del recibo que se entrega al productor |
| `payment_app/ui_payment/auth_flow.py:40,52` | Título y encabezado del login de pagos |
| `payment_app/ui_payment/dashboard.py:36` | Título de la ventana de pagos |
| `admin_app/ui_admin/login_window.py:32,41` | Título y encabezado del login de admin |
| `admin_app/ui_admin/dashboard.py:34` | Título de la ventana de admin |
| `admin_app/main_admin.py:19`, `payment_app/main_payment.py:21` | `setApplicationName` (barra de tareas) |
| `backend/app.py:20` | Título de la API en `/docs` |

**Interno** (docstrings y encabezados): `backend/app.py:2`, `core/audit.py:2`, `core/models.py:2`, `core/utils.py:2`, `core/xaman_client.py:1`, `shared_ui/__init__.py:2`, `shared_ui/components.py:2`, `tests/test_core.py:2`, `requirements.txt:1`.

*3. Documentación*
- `README.md`: sección "Multicadena" con el diagrama de arquitectura, la tabla de equivalencia de escrow XRPL ↔ Stellar y la nota de billetera dual. Actualizar el título, la tabla del stack (`stellar-sdk`) y el árbol del proyecto (`coffee-payments/`).
- `QUICKSTART.md`: dependencia nueva, migración 004, cómo fondear cuentas de testnet con friendbot, y corregir las rutas al nombre nuevo. **Ojo:** la línea 186 tiene un enlace `file:///c:/Users/eric/Desktop/software/...` roto desde hace tiempo — cambiarlo por una ruta relativa.
- `backend/README.md`: título y el `cd coffee_xrpl_platform/backend` de la línea 33.
- `AUDITORIA.md`: por qué se descartaron los *claimable balances* (invariante I3) y las diferencias de modelo de seguridad entre ambos escrows.
- `PLAN_IMPLEMENTACION.md`: solo el título; el resto es histórico y no se reescribe.

**Fuera de alcance.** Funcionalidad nueva. Renombrar directorios de paquetes de Python (`payment_app/`, `admin_app/`) — los nombres de módulo no son visibles para el usuario y renombrarlos rompería imports por todo el proyecto sin ganancia.

**Criterios de aceptación.**
- `grep -ri "coffee.xrpl\|coffee_xrpl" .` no devuelve nada fuera de los planes históricos.
- La instrucción de firma en Xaman y el PDF del recibo dicen "Coffee Payments".
- La migración 005 corre sobre una copia de la base de datos real y es idempotente.
- Alguien que no conoce el proyecto puede levantarlo en ambas redes siguiendo solo el `QUICKSTART.md`.
- Suite completa en verde.

**Pruebas.** Suite completa; arranque de ambas apps verificando los títulos; generación de un recibo PDF; prueba en limpio del `QUICKSTART.md` sobre una base de datos nueva.

---
---

## Propiedad de archivos

Fuente de verdad para evitar conflictos. Si dos issues quieren tocar el mismo archivo, van en serie.

| Archivo | Issue dueña | Toques posteriores |
|---|---|---|
| `scripts/spike_stellar.py` | XLM-01 | — |
| `scripts/spike_stellar_escrow.py` | XLM-02 | — |
| `scripts/spike_lobstr.py` | XLM-03 | — |
| `core/ledger/base.py`, `__init__.py` | XLM-04 | XLM-12 (métodos de escrow) |
| `core/ledger/xrpl.py`, `core/rates.py`, `core/xrpl_client.py` | XLM-04 | — |
| `core/ledger/stellar.py` | XLM-05 | XLM-12 (escrow) |
| `core/models.py`, `scripts/migrate_004_*` | XLM-06 | — |
| `core/iso_generator.py` | XLM-07 | XLM-16 (camt.053), XLM-13 (pacs.002) |
| `producer_view.py` | XLM-06 (línea 323) | XLM-08 |
| `user_management.py`, `core/utils.py` | XLM-08 | — |
| `core/wallet_session.py`, `auth_flow.py`, `main_payment.py` | XLM-09 | XLM-19 (cableado) |
| `payment_flow.py` | XLM-10 | XLM-19 (cableado) |
| `dashboard.py` (payment) | XLM-11 | — |
| `escrow_view.py` | XLM-13 | XLM-17 (X5), XLM-19 (cableado) |
| `history_view.py`, `payment_detail_dialog.py`, `core/receipt.py` | XLM-14 | — |
| `metrics_view.py` | XLM-15 | — |
| `audit_view.py` | XLM-16 | — |
| `shared_ui/sign_dialog.py`, `xaman_sign_dialog.py` | XLM-17 | — |
| `backend/*` | XLM-18 | — |
| `core/lobstr_client.py`, `settings_dialog.py` | XLM-19 | — |
| `README.md`, `QUICKSTART.md`, `AUDITORIA.md`, `backend/README.md` | XLM-20 | — |
| `tests/test_core.py` | todos | coordinar: añadir, nunca reescribir |

**Excepción — XLM-20.** El renombrado de producto (`Coffee XRPL Platform` → `Coffee Payments`) barre ~25 archivos que en la tabla pertenecen a otros issues. Por eso va en la última ola: cuando corre, ninguno de esos issues sigue en vuelo. Ningún otro issue debe tocar esa cadena por su cuenta — se deja tal cual y XLM-20 la limpia toda de una pasada.

---

## Hoja de publicación

Orden de publicación y etiquetas exactas. El orden importa: al publicar de arriba abajo, cada issue ya puede citar por número a los que la bloquean.

| # | Título del issue | Etiquetas | Bloqueada por |
|---|---|---|---|
| 01 | `[XLM-01] Spike: pagos básicos en Stellar Testnet` | `research` `backend` `complexity: medium` `stellar-multichain` | — |
| 02 | `[XLM-02] Spike: escrow con transacciones preautorizadas` | `research` `backend` `complexity: high` `stellar-multichain` | — |
| 03 | `[XLM-03] Spike: firma remota con LOBSTR` | `research` `complexity: high` `stellar-multichain` | — |
| 04 | `[XLM-04] Protocolo LedgerClient y shim de XRPLClient` | `backend` `complexity: medium` `stellar-multichain` | — |
| 06 | `[XLM-06] Modelo de datos multicadena` | `backend` `complexity: high` `stellar-multichain` | — |
| 05 | `[XLM-05] StellarClient: pagos, saldo, activación` | `backend` `complexity: high` `stellar-multichain` | 01, 04 |
| 07 | `[XLM-07] ISO 20022 parametrizado por red` | `backend` `complexity: medium` `stellar-multichain` | 04 |
| 08 | `[XLM-08] Alta de direcciones Stellar` | `frontend` `good first issue` `complexity: medium` `stellar-multichain` | 06 |
| 09 | `[XLM-09] WalletSession y conexión perezosa` | `frontend` `complexity: high` `stellar-multichain` | 04, 06 |
| 14 | `[XLM-14] Historial, detalle y recibo por red` | `frontend` `complexity: medium` `stellar-multichain` | 06 |
| 15 | `[XLM-15] Métricas de admin por red` | `frontend` `good first issue` `complexity: low` `stellar-multichain` | 06 |
| 18 | `[XLM-18] Backend: endpoints de firma para Stellar` | `backend` `complexity: high` `stellar-multichain` | 03 |
| 10 | `[XLM-10] Selector de red y pago directo en Stellar` | `frontend` `complexity: high` `stellar-multichain` | 05, 06, 07, 09 |
| 11 | `[XLM-11] Doble saldo en el dashboard` | `frontend` `good first issue` `complexity: medium` `stellar-multichain` | 05, 09 |
| 12 | `[XLM-12] Escrow de Stellar en StellarClient` | `backend` `complexity: high` `stellar-multichain` | 02, 05, 06 |
| 16 | `[XLM-16] camt.053 por red` | `backend` `complexity: medium` `stellar-multichain` | 06, 07 |
| 13 | `[XLM-13] escrow_view multicadena` | `frontend` `complexity: high` `stellar-multichain` | 09, 12 |
| 17 | `[XLM-17] SignDialog genérico y cierre de la Fase X5` | `frontend` `complexity: high` `stellar-multichain` | 13 |
| 19 | `[XLM-19] Cliente LOBSTR y cableado en la app` | `frontend` `backend` `complexity: high` `stellar-multichain` | 10, 17, 18 |
| 20 | `[XLM-20] Limpieza, tests finales y documentación` | `backend` `documentation` `complexity: medium` `stellar-multichain` | todos |

**Antes de publicar:** `PLAN_STELLAR.md` y este documento tienen que estar en la rama por defecto del repositorio. Todos los issues los citan como contexto; sin ellos en GitHub, un contribuyente externo no puede tomar el trabajo.

**Idioma:** español, consistente con `PLAN_STELLAR.md`, con la UI de la plataforma y con el resto de la documentación que el contribuyente necesita leer para trabajar. Los docstrings y comentarios del código siguen en inglés, según la regla del proyecto.
