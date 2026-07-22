# Plan de Implementación — Multicadena XRPL + Stellar y Billetera Dual

**Origen:** Decisión de producto (2026-07-22). La plataforma deja de ser mono-cadena: opera XRPL y Stellar desde una misma interfaz, con billetera dual (Xaman para XRPL, la app de MicoPay para Stellar).

> ## ♻️ Enmienda — 2026-07-22, misma fecha, después de publicar los issues
>
> **La billetera de Stellar deja de ser LOBSTR y pasa a ser la app de MicoPay.**
>
> LOBSTR era el único riesgo del plan que podía terminar en "no se puede": no expone un API de solicitudes de firma, WalletConnect v2 no tiene cliente *dapp* en Python, y su Vault exige multifirma sobre mainnet. Se controlaba un solo extremo.
>
> La app de MicoPay ya firma del lado del cliente con las llaves en el Keychain/Keystore nativo, vive en [`micopay/frontend`](https://github.com/Micopay/micopay-protocol/tree/main/micopay/frontend) (Capacitor + React + TypeScript) y tiene su backend en `micopay/backend`. Al ser primera parte, la pregunta deja de ser *si se puede* y pasa a ser *cuándo se construye*.
>
> **Qué cambia:**
> - **S0.3** deja de investigar LOBSTR. Ahora especifica el contrato de firma delegada y verifica si el contrato Soroban [`contracts/htlc-core`](https://github.com/Micopay/micopay-protocol/tree/main/contracts/htlc-core) sirve para el escrow de calidad.
> - **S7** deja de implementar un cliente de LOBSTR. Implementa `MicopaySigner` contra los endpoints de `micopay/backend`.
> - Los endpoints y la pantalla de aprobación **no viven en este repositorio**: son [micopay-protocol#323](https://github.com/Micopay/micopay-protocol/issues/323) y [#324](https://github.com/Micopay/micopay-protocol/issues/324).
>
> **Qué NO cambia:** nada de S1 a S6. La abstracción `Signer` (D1) se diseñó justo para que la elección de billetera no se filtrara al resto del plan, y cumplió.
>
> **Posible simplificación pendiente de verificar:** si `htlc-core` acepta beneficiario fijo y `claim(preimage)` con ventana configurable, sustituye al diseño D4 de transacciones preautorizadas y mejora la paridad — el preimage vuelve a ser la llave igual que el fulfillment en XRPL, sin cuenta efímera ni reserva de 2 XLM. Lo decide S0.3.

**Ejecutor previsto:** Claude. Documento autocontenido; no requiere leer otra conversación.
**Concepto:** Todo lo que hoy existe sobre XRPL — pagos directos, escrow contra calidad, mensajería ISO 20022, historial, métricas — debe existir igual sobre Stellar. El operador elige la red en el momento de pagar; el resto de la plataforma no cambia de forma.

---

## Arquitectura elegida (leer antes de todo)

Dos ejes de abstracción independientes. **La red** (dónde se liquida) y **el firmante** (quién autoriza) se combinan libremente:

```
                    ┌───────────────────────────────────────────┐
                    │              payment_flow                 │
                    │   selecciona (red, token, modo, firmante) │
                    └───────────────┬───────────────────────────┘
                                    │
              ┌─────────────────────┴─────────────────────┐
              ▼                                           ▼
   ┌────────────────────┐                      ┌────────────────────┐
   │   LedgerClient     │  (Protocol)          │      Signer        │  (Protocol)
   ├────────────────────┤                      ├────────────────────┤
   │ XRPLClient         │                      │ SeedSigner(XRPL)   │
   │ StellarClient      │                      │ SeedSigner(STELLAR)│
   └────────────────────┘                      │ XamanSigner        │
                                               │ MicopaySigner      │
                                               └────────────────────┘
```

**Invariantes — no violar:**

- **I1.** Ninguna llave privada llega al backend. Se mantiene lo establecido en `PLAN_XAMAN.md` (I1–I4) y aplica igual a Stellar.
- **I2.** `Payment.network` es obligatorio y no se infiere. Un pago sabe en qué cadena se liquidó, siempre.
- **I3.** El escrow de Stellar debe ser **tan restrictivo como el de XRPL**: los fondos bloqueados solo pueden terminar en el productor o de vuelta en el operador después del vencimiento. Ningún diseño que permita a la cooperativa redirigir fondos a un tercero es aceptable.
- **I4.** Ninguna fase deja `pytest tests/ -v` en rojo, y XRPL sigue funcionando exactamente igual hasta el final.

---

## Prerrequisitos

1. **Reglas generales del proyecto** (de `PLAN_IMPLEMENTACION.md`): UI en español; docstrings y comentarios en inglés; estilo PySide6 existente con `get_session()`/`close_session()` en try/finally; un commit por tarea con mensaje en español; verificación por fase (`pytest tests/ -v` + humo de ambas apps).
2. **Dependencia nueva:** `stellar-sdk>=15.0.0` en `requirements.txt` raíz (requiere Python ≥3.10; el proyecto ya pide 3.11+). No se añade nada al backend hasta la Fase S7.
3. **Cuentas de prueba:** dos cuentas de Stellar Testnet fondeadas con friendbot (`https://friendbot.stellar.org?addr=<G...>`). Horizon testnet: `https://horizon-testnet.stellar.org`. Explorador: `https://stellar.expert/explorer/testnet/tx/{hash}`.
4. **Deuda previa a considerar:** la Fase X5 de `PLAN_XAMAN.md` (escrow firmado con Xaman) sigue abierta — `escrow_view.py:98` deshabilita los botones cuando no hay seed. La Fase S7 de este plan generaliza el diálogo de firma, que es justo lo que X5 necesita. **Recomendación:** cerrar X5 durante S7, no antes, para no hacer el trabajo dos veces.

---

## Decisiones de Diseño (D)

### D1. Abstracción por `Protocol`, no por herencia
`core/ledger/base.py` define `LedgerClient` como `typing.Protocol`. `XRPLClient` ya cumple casi toda la interfaz sin tocarlo (`get_balance`, `verify_transaction`, `validate_address`, `create_escrow`, `finish_escrow`, `cancel_escrow`). No se introduce una clase base abstracta ni se reescribe el cliente XRPL: se mueve, se le añaden los métodos que falten y se declara conforme. Menos churn, menos riesgo de romper lo que funciona.

### D2. La red es un dato de primera clase
`Network` como enum de strings (`"XRPL"`, `"STELLAR"`). Se persiste en `Wallet.network`, `Payment.network` y `EscrowDetail.network`. Nunca se representa como booleano ni se deduce del prefijo de la dirección.

### D3. Direcciones en tabla `wallets` con shim de compatibilidad
De las 57 referencias a `xrpl_address` en el código, **solo una es consulta SQL** (`producer_view.py:323`, `filter_by(xrpl_address=xrpl)`). Las otras 56 son lecturas de atributo, interceptables con `@property`. Por eso la tabla genérica cuesta casi lo mismo que añadir columnas, y no vuelve a costar nada cuando llegue una tercera cadena.

```python
class Wallet(Base):
    __tablename__ = "wallets"
    id         = Column(Integer, primary_key=True)
    owner_type = Column(String(20), nullable=False)   # 'producer' | 'user'
    owner_id   = Column(Integer,    nullable=False)
    network    = Column(String(20), nullable=False)   # 'XRPL' | 'STELLAR'
    address    = Column(String(100), nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("network", "address", name="uq_wallet_net_addr"),)
```

El shim mantiene vivo todo el código actual:

```python
class Producer(Base):
    def address_for(self, network: str) -> str | None: ...

    @property
    def xrpl_address(self) -> str | None:       # legacy shim — 56 lecturas intactas
        return self.address_for("XRPL")
```

Beneficio adicional: se acaba el problema del `NOT NULL UNIQUE` en `Producer.xrpl_address`, que impedía registrar un productor que solo opere en Stellar.

### D4. Escrow Stellar = cuenta efímera + dos transacciones preautorizadas
Stellar no tiene operación de escrow. Los *claimable balances* **no sirven** aquí: sus predicados son solo temporales (no existe predicado de preimagen), así que el productor podría cobrar cuando quisiera antes del vencimiento y desaparecería la compuerta de calidad — violando I3.

El equivalente exacto es una cuenta escrow de un solo uso con dos transacciones preautorizadas mutuamente excluyentes:

```
1. CreateAccount(escrow, monto + 2.0 XLM de reserva)        [firma: operador]
   → la cuenta escrow nace con secuencia S

2. Construir, sin enviar, ambas alternativas con secuencia S+2:
   TX_LIBERAR  = [Payment(escrow → productor, monto),
                  AccountMerge(escrow → operador)]           sin timebounds
   TX_REEMBOLSO= [AccountMerge(escrow → operador)]           minTime = T

3. TX_SETUP (secuencia S+1)                                  [firma: llave efímera]
   [SetOptions(signer = preAuthTx(hash(TX_LIBERAR)),  weight 1),
    SetOptions(signer = preAuthTx(hash(TX_REEMBOLSO)), weight 1),
    SetOptions(master_weight = 0, thresholds low/med/high = 1)]

4. Se descarta la llave efímera. Se guardan ambos XDR en la base de datos.
```

A partir del paso 4 la cuenta escrow es un autómata: **solo puede ejecutarse una de las dos transacciones** (comparten secuencia S+2, la primera en confirmar invalida la otra), y ningún tercero puede mover los fondos porque la llave maestra tiene peso 0.

| Acción XRPL | Equivalente Stellar |
|---|---|
| `EscrowCreate` | `CreateAccount` + `TX_SETUP` |
| `EscrowFinish` con fulfillment | enviar `TX_LIBERAR` |
| `EscrowCancel` tras `CancelAfter` | enviar `TX_REEMBOLSO` (`minTime` lo garantiza) |
| El fulfillment es la llave de liberación | **El XDR de `TX_LIBERAR` es la llave de liberación** |

Esto conserva la tesis educativa del proyecto: igual que hoy el `fulfillment` viaja dentro del `pacs.002` y desbloquea el escrow XRPL, en Stellar viaja el XDR preautorizado. El mensaje bancario sigue siendo, literalmente, la llave.

**Detalles que hay que respetar:**
- La reserva mínima es `(2 + subentradas) × 0.5 XLM`; con dos firmantes son **2.0 XLM**, recuperados por el `AccountMerge` en cualquiera de los dos desenlaces.
- El hash de una transacción preautorizada incluye la comisión. Fijar `base_fee` holgada (10 000 stroops) al construirlas; si aun así el envío fallara por congestión, envolver en un **fee-bump** (no altera el hash interno).
- La secuencia inicial de una cuenta Stellar recién creada es `ledger_seq << 32`. Leerla de Horizon después del paso 1 en vez de calcularla.

### D5. `EscrowDetail` se generaliza con `chain_data` JSON
Los campos comunes se quedan como columnas (`payment_id`, `network`, `cancel_after`, `create_tx_hash`, `finish_tx_hash`, `cancel_tx_hash`, `quality_notes`, `resolved_at`). Lo específico de cada cadena va a una columna `chain_data` (texto JSON):

- XRPL → `{"offer_sequence": 42, "condition_hex": "A02580...", "fulfillment_hex": "A02280..."}`
- Stellar → `{"escrow_account": "G...", "release_xdr": "AAAA...", "refund_xdr": "AAAA...", "sequence": "..."}`

Las tres columnas XRPL actuales se migran a `chain_data` y se eliminan. `ALTER TABLE ... DROP COLUMN` existe desde SQLite 3.35; la migración comprueba `sqlite3.sqlite_version` y, si es menor, reconstruye la tabla.

### D6. Conexión perezosa de billetera
`AuthFlowDialog` deja de devolver `xrpl_seed` o `xaman_client` sueltos y devuelve un `WalletSession`: un contenedor de firmantes indexado por red, con un método `signer_for(network)` que **pide la credencial la primera vez que se necesita**. Al iniciar sesión se conecta una sola billetera; la segunda se solicita cuando el operador elige esa red por primera vez. Sin esto, la interfaz dual obligaría a conectar dos billeteras aunque solo se vaya a usar una.

### D7. Activación de cuenta: `CreateAccount` frente a `Payment`
En XRPL un `Payment` a una dirección sin fondear crea la cuenta si cubre la reserva. En Stellar **no**: falla con `op_no_destination`. Antes de pagar hay que consultar si la cuenta destino existe y, si no, usar `CreateAccount` con al menos 1 XLM. La interfaz muestra el estado "cuenta no activada" en la ficha del productor y ajusta el monto mínimo. Esta comprobación vive en `StellarClient.account_exists(address)`.

### D8. El memo de Stellar no admite el UETR
`MemoText` está limitado a **28 bytes** y el memo actual (`f"Coffee Payment - UETR: {uetr}"`) mide más de 50. En Stellar se usa `MemoHash` con los 16 bytes crudos del UUID del UETR, rellenados a 32 bytes. La correlación con ISO 20022 se conserva íntegra y verificable en el explorador; solo cambia la codificación.

### D9. ISO 20022 parametrizado por red
`core/iso_generator.py` tiene `"XRPL"` fijo en `ClrSysMmbId` (líneas 139 y 158) y emite `<XRPLTxHash>` en los datos suplementarios. Se parametriza por red: `ClrSysMmbId` toma `"XRPL"` o `"STELLAR"`, y el elemento pasa a `<LedgerTxHash Network="STELLAR">`. Para XRPL se conserva `<XRPLTxHash>` de modo que los mensajes nuevos sigan siendo idénticos a los ya almacenados. `generate_pacs002` recibe `result_code` genérico (`xrpl_result_code` queda como alias en desuso) y mapea también los códigos de Stellar: `tx_success` → ACSC; cualquier `tx_*`/`op_*` de error → RJCT con el código en `StsRsnInf`.

### D10. Migración sin big-bang
XRPL sigue siendo la red por defecto en toda la interfaz. Stellar aparece solo cuando el operador lo elige. Cada fase termina con los tests en verde y ambas apps arrancando. El orden S1 → S2 es deliberado: primero la capa de red (que no toca la base de datos), después el modelo de datos (que sí).

### D11. El backend crece, no se duplica
Los endpoints de Stellar viven en el mismo FastAPI (`backend/app.py`), reutilizando `require_device` y el patrón de `SignRequestLog`. No se crea un segundo servicio.

---

## FASE S0 — Spikes Técnicos (de-risk, standalone, sin tocar la app)

Tres scripts independientes en `scripts/`, sin importar nada de la app, siguiendo el patrón de `spike_escrow.py` y `spike_xaman.py`.

### S0.1 `scripts/spike_stellar.py` — pagos básicos
1. Crear dos cuentas testnet con friendbot; imprimir direcciones y saldos.
2. Pago de 10 XLM de A a B con `MemoHash` derivado de un UETR (D8); verificar en Horizon e imprimir la URL de stellar.expert.
3. Pago a una **cuenta inexistente**: confirmar que falla con `op_no_destination`, y que `CreateAccount` sí funciona (D7).
4. Validación de direcciones con `StrKey.is_valid_ed25519_public_key`, incluyendo casos inválidos y una dirección XRPL (debe rechazarla).

### S0.2 `scripts/spike_stellar_escrow.py` — el escrow de D4 completo
1. Ciclo feliz: crear escrow con ventana de 2 minutos → enviar `TX_LIBERAR` → verificar que el productor recibió el monto y el operador recuperó la reserva.
2. Ciclo de reembolso: crear escrow → esperar el vencimiento → enviar `TX_REEMBOLSO` → verificar el retorno de fondos.
3. **Pruebas negativas, obligatorias (I3):** confirmar que `TX_REEMBOLSO` es rechazada antes de `minTime`; que `TX_LIBERAR` ya no es válida después de ejecutarse `TX_REEMBOLSO` (y viceversa); y que con la llave efímera descartada nadie puede construir una transacción alternativa que saque los fondos.
4. Imprimir el costo real en XLM de un ciclo completo.

### S0.3 Contrato de firma MicoPay y viabilidad de `htlc-core` (ver enmienda)
Probar, en este orden, hasta que uno funcione:
1. **Contrato de firma delegada**: especificar `POST /sign-requests`, `GET /sign-requests/{id}` y `POST /sign-requests/{id}/resolve` copiando la forma de la API de Xaman, para que el escritorio no tenga que ramificar. Diseñarlo como primitiva de plataforma, no como feature de esta app.
2. **Viabilidad de `htlc-core`** para el escrow de calidad: ¿beneficiario fijo al crear el lock? ¿ventana temporal configurable por operación? ¿reembolso permissionless tras vencimiento? ¿desplegado en testnet y con qué ID? Si cumple, sustituye al diseño D4.

**Criterio de aceptación:** S0.1 y S0.2 corren de punta a punta en testnet. **S0.3 puede fallar y eso es un resultado válido**, no un bloqueo: su conclusión se escribe en el encabezado del script y determina el alcance de la Fase S7. Todo lo demás avanza con modo seed.

---

## FASE S1 — Capa de Red (`core/ledger/`)

```
core/ledger/
├── __init__.py     # get_ledger(network) -> LedgerClient  |  Network enum
├── base.py         # Protocol LedgerClient
├── xrpl.py         # XRPLClient (movido tal cual desde core/xrpl_client.py)
└── stellar.py      # StellarClient (nuevo)
```

### S1.1 El protocolo (`base.py`)
```python
class LedgerClient(Protocol):
    network: str          # 'XRPL' | 'STELLAR'
    native_asset: str     # 'XRP'  | 'XLM'
    decimals: int         # 6      | 7

    def validate_address(self, address: str) -> bool: ...
    def account_exists(self, address: str) -> bool: ...
    def get_balance(self, address: str) -> dict: ...          # {'native': float, 'raw': str}
    def build_payment(self, source, destination, amount, memo_uetr) -> object: ...
    def submit_signed(self, signed) -> dict: ...              # {'hash', 'validated', 'result'}
    def verify_transaction(self, tx_hash: str) -> dict: ...
    def explorer_url(self, tx_hash: str) -> str: ...
```

### S1.2 `core/xrpl_client.py` se convierte en shim
El archivo original se mueve a `core/ledger/xrpl.py` y en su lugar queda un reexport (`from core.ledger.xrpl import *`) para no tocar los 15 archivos que lo importan. Se le añade `account_exists` y `explorer_url` (alias del actual `get_testnet_explorer_url`). `MOCK_EXCHANGE_RATES` gana `XLM_MXN` y se mueve a `core/rates.py` con las funciones de conversión.

### S1.3 `StellarClient` (`stellar.py`)
Horizon testnet, `Network.TESTNET_NETWORK_PASSPHRASE`, montos como `Decimal` de 7 decimales, `base_fee` 100 stroops por operación, memo según D8, activación según D7. Métodos de escrow (`create_escrow`, `finish_escrow`, `cancel_escrow`) con la firma equivalente a los de XRPL pero implementando D4, devolviendo en el diccionario los datos que irán a `chain_data`.

**Tests S1:** validación de direcciones de ambas redes cruzadas (una dirección XRPL debe fallar en Stellar y viceversa), conversión de montos, construcción del memo, `get_ledger()` devolviendo la clase correcta. Sin red: mockear Horizon y el JsonRpcClient.

---

## FASE S2 — Modelo de Datos Multicadena

### S2.1 Modelos (`core/models.py`)
- Nueva tabla `Wallet` (D3) con relaciones a `Producer` y `User`.
- `Producer` / `User`: métodos `address_for(network)`, `set_address(network, address)` y la `@property xrpl_address` de compatibilidad.
- `Payment`: `+ network` (no nulo, por defecto `'XRPL'`), y `xrpl_tx_hash` se renombra a `tx_hash` con `@property xrpl_tx_hash` de compatibilidad.
- `EscrowDetail`: `+ network`, `+ chain_data` (texto JSON); se eliminan `offer_sequence`, `condition_hex`, `fulfillment_hex` (D5).
- Nuevo `PaymentStatus` no hace falta: los estados actuales sirven igual en ambas cadenas.

### S2.2 Migración (`scripts/migrate_004_multichain.py`)
Idempotente, con respaldo previo en `data/backups/` como los migradores existentes:
1. `CREATE TABLE wallets`.
2. Copiar `producers.xrpl_address` y `users.xrpl_address` a `wallets` con `network='XRPL'`, `is_default=1`.
3. `ALTER TABLE payments RENAME COLUMN xrpl_tx_hash TO tx_hash`; `ADD COLUMN network` con relleno `'XRPL'`.
4. `escrow_details`: añadir `network` y `chain_data`; volcar las tres columnas XRPL a JSON; eliminarlas (o reconstruir la tabla si SQLite < 3.35).
5. Dejar `producers.xrpl_address` / `users.xrpl_address` en la tabla pero sin uso (columnas muertas). Se eliminan en S8, una vez probado todo, para tener vuelta atrás durante el desarrollo.

### S2.3 El único punto de consulta
`payment_app/ui_payment/producer_view.py:323` cambia de `filter_by(xrpl_address=xrpl)` a una consulta sobre `Wallet` por `(network, address)`. Es el **único** cambio obligatorio de este tipo en todo el proyecto.

**Tests S2:** el shim devuelve la misma dirección que antes de migrar; un productor solo-Stellar es válido; la unicidad de `(network, address)` se respeta; `chain_data` sobrevive el viaje de ida y vuelta a JSON. Los 8 usos de `xrpl_address` en `tests/test_core.py` deben seguir pasando sin modificarse — esa es la prueba de que el shim funciona.

---

## FASE S3 — Alta de Direcciones Stellar

- `producer_view.py`: segundo campo de dirección (Stellar), validación con `StrKey`, indicador de "cuenta no activada" (D7). Al menos una dirección es obligatoria; ya no específicamente la de XRPL.
- `user_management.py` (admin): campo de dirección Stellar del operador. **`generate_user_id()` sigue derivándose de la dirección XRPL** — los IDs ya emitidos no pueden cambiar. Para un operador solo-Stellar, generar el ID desde su dirección Stellar; documentar la regla en el docstring de `core/utils.py`.
- Vista de ficha del productor: mostrar ambas direcciones con su estado.

**Tests S3:** validación cruzada de direcciones, alta de productor con una sola red, alta con ambas, rechazo de duplicados por red.

---

## FASE S4 — Pago Directo en Stellar (modo seed) — hito de valor

- `payment_flow.py`: selector de red (`QRadioButton` XRPL/Stellar) sobre el selector de token; el combo de tokens se filtra por red (XRP/USDC/RLUSD/MXN frente a XLM/USDC/MXN); la red se deshabilita si el productor no tiene dirección en ella, con tooltip explicativo.
- `_do_payment` y `_persist_payment` dejan de hablar con `self.xrpl_client` y hablan con `get_ledger(network)`. `Payment.network` se persiste.
- `dashboard.py`: dos saldos en el encabezado, cada uno en su `FunctionWorker` (ya existe el patrón), con indicador independiente de conexión por red.
- `auth_flow.py` + `main_payment.py`: `WalletSession` con conexión perezosa (D6). En modo seed, el paso 3 pide el seed de la red elegida al iniciar sesión y el de la otra cuando haga falta.
- ISO 20022 parametrizado (D9) y activación de cuenta (D7) integrados en el flujo.

**Verificación S4:** pago real en Stellar Testnet desde la app, con `pacs.008` / `camt.054` generados, hash verificable en stellar.expert y saldo actualizado. Un pago XRPL en la misma sesión debe seguir comportándose exactamente igual que antes.

---

## FASE S5 — Escrow en Stellar (modo seed)

- `StellarClient` implementa D4 completo, reutilizando lo validado en S0.2.
- `escrow_view.py`: columna **Red** en la tabla; los botones Aprobar / Rechazar / Reembolsar despachan por red según la fila seleccionada. La lógica de habilitación (`_update_buttons`) ya depende de `cancel_after`, que es común a ambas cadenas — se mantiene.
- Reutilizar el generador de preimagen de `core/security.py::generate_escrow_condition` **solo para XRPL**. En Stellar la llave es el XDR de `TX_LIBERAR`; el `pacs.002` ACSC lo transporta en el mismo lugar donde hoy va el fulfillment (`generate_pacs002(..., escrow_fulfillment=...)` pasa a aceptar cualquiera de los dos y etiqueta cuál es).
- Regla de tiempos: en Stellar, a diferencia de XRPL, **sí sería posible** liberar después del vencimiento mientras nadie haya enviado `TX_REEMBOLSO`. Para no confundir al operador con dos reglas distintas, la interfaz mantiene el mismo comportamiento que XRPL (liberar solo antes del vencimiento) y se documenta la diferencia en el docstring del módulo.

**Verificación S5:** ciclo completo en testnet por ambas redes — crear → aprobar → liberar, y crear → rechazar → esperar → reembolsar — con ventanas cortas.

---

## FASE S6 — Historial, Métricas e ISO Multicadena

- `history_view.py`: columna Red con icono, filtro por red junto al de estado, enlace al explorador correcto.
- `payment_detail_dialog.py` y `core/receipt.py`: mostrar red y usar la URL de explorador correspondiente.
- `metrics_view.py` (admin): desglose por red además del total; la gráfica de barras conserva su forma, con series por red.
- `audit_view.py` — cierre de día: el `camt.053` se genera **por red** (un estado de cuenta por cadena), porque cada uno declara una cuenta y una divisa de liquidación distintas. Nombrar los archivos con el sufijo de red.

**Tests S6:** `camt.053` correcto para un período con pagos de ambas redes; filtros del historial; totales de métricas por red.

---

## FASE S7 — Firma con la app de MicoPay (alcance definido por S0.3)

Solo se ejecuta con el resultado del spike en la mano.

- Los endpoints (`POST /sign-requests`, `GET /sign-requests/{id}`, `POST /sign-requests/{id}/resolve`) viven en `micopay/backend` — [micopay-protocol#323](https://github.com/Micopay/micopay-protocol/issues/323) — y la pantalla de aprobación en `micopay/frontend` — [#324](https://github.com/Micopay/micopay-protocol/issues/324). Aquí solo se implementa `core/micopay_client.py`, réplica de `core/xaman_client.py` con otra URL base. El envío a Horizon lo hace el escritorio tras recuperar el XDR firmado.
- **Si SEP-7 no funciona:** implementar el sidecar de WalletConnect v2 o, si tampoco es viable en el plazo, dejar Stellar en modo seed y documentar la limitación en `README.md`. **No es un bloqueo del plan**: S4 y S5 ya entregaron la funcionalidad completa.
- `xaman_sign_dialog.py` se generaliza a `shared_ui/sign_dialog.py`: el QR, el polling, el timeout y `resolve_status()` ya son agnósticos; solo hay que parametrizar el cliente y el texto. **Aquí se cierra la Fase X5 de `PLAN_XAMAN.md`** (escrow firmado con Xaman), que necesita exactamente esta generalización.
- `settings_dialog.py`: sección de MicoPay junto a la de Xaman, con las mismas claves cifradas en `AppConfig`.

**Verificación S7:** pago y escrow en Stellar firmados desde el teléfono, sin seed en la app; y el escrow XRPL con Xaman funcionando por fin.

---

## FASE S8 — Limpieza, Tests y Documentación

- Eliminar las columnas muertas `producers.xrpl_address` y `users.xrpl_address` (`migrate_005_drop_legacy_address.py`).
- `pytest tests/ -v` completo en verde, con tests nuevos de Stellar, `wallets`, escrow preautorizado e ISO por red.
- `README.md`: sección "Multicadena" con el diagrama de arriba, la tabla de equivalencia de escrow (D4) y la nota de billetera dual. Actualizar la tabla del stack (`stellar-sdk`) y la estructura del proyecto.
- `QUICKSTART.md`: dependencia nueva, migración 004 y cómo fondear cuentas de testnet con friendbot.
- `AUDITORIA.md`: nota sobre las diferencias de modelo de seguridad entre ambos escrows y por qué se descartaron los claimable balances (I3).

---

## Resumen de Secuencia

| Fase | Contenido | Riesgo | Dependencia |
|------|-----------|--------|-------------|
| S0 | Spikes: pagos, escrow preautorizado, contrato de firma y `htlc-core` | Alto (por eso va primero) | Cuentas testnet |
| S1 | Capa `core/ledger/` + `StellarClient` | Medio | S0.1 |
| S2 | Tabla `wallets`, `network` en pagos y escrows, migración | Medio-alto (toca datos) | S1 |
| S3 | Alta de direcciones Stellar en ambas apps | Bajo | S2 |
| S4 | Pago directo Stellar + selector de red + doble saldo | Medio | S1–S3 |
| S5 | Escrow Stellar con transacciones preautorizadas | Alto | S0.2, S4 |
| S6 | Historial, métricas y camt.053 por red | Bajo | S4 |
| S7 | Firma con la app de MicoPay + cierre de la Fase X5 de Xaman | Medio (ya no depende de un tercero) | S0.3, S4, micopay#323/#324 |
| S8 | Limpieza, tests y documentación | Bajo | Todo probado |

**Hito mínimo de valor:** S0–S4 ya entrega una plataforma multicadena real — el operador paga en XRPL o en Stellar desde la misma pantalla, con la misma mensajería ISO 20022. S5 iguala el escrow, S6 iguala la trazabilidad y S7 completa la billetera dual.

**Punto de no retorno:** S2. Es la única fase que modifica datos existentes. Respaldo obligatorio antes de ejecutar la migración y verificación de que los 8 usos de `xrpl_address` en los tests pasan sin tocarse.

---

## Apéndice — Lo que este plan deliberadamente NO hace

- **No implementa Soroban.** Un contrato de escrow en Rust/WASM sería más flexible y más vistoso que el patrón de transacciones preautorizadas, pero exige toolchain de Rust y despliegue de contrato. El diseño de D4 es autocontenido en Python y suficiente. Si más adelante se quiere Soroban, entra como una tercera implementación de `LedgerClient.create_escrow` sin tocar el resto.
- **No unifica las billeteras todavía.** Este plan mantiene Xaman para XRPL porque ya está implementado y probado. Cuando la app de MicoPay sume XRPL — está en su hoja de ruta — puede sustituir a Xaman y el operador dejaría de tener dos apps. La abstracción `Signer` deja esa puerta abierta sin tocar nada más.
- **No toca tokens reales.** USDC y RLUSD siguen simulados en ambas redes. Un USDC real en Stellar exige que el productor establezca una *trustline* con el emisor antes de poder cobrar — un flujo de onboarding completo que merece su propio plan.
- **No aborda puentes ni intercambio entre cadenas.** Multicadena aquí significa "dos rieles paralelos con una interfaz común", no interoperabilidad entre ellos.
