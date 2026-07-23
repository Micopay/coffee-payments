#!/usr/bin/env python3
"""
Spike Stellar Testnet Integration (Ola 0 - S0.1 / XLM-01)

===============================================================================
LECCIONES APRENDIDAS Y REGLAS DE DISEÑO DE ARQUITECTURA
===============================================================================

1. Formato del memo para el UETR
En Stellar, un MemoText tiene un límite de 28 bytes (ASCII/UTF-8). Esto significa que un UETR estándar (UUID v4 de 36 caracteres con guiones, 
por ejemplo 123e4567-e89b-12d3-a456-426614174000) no puede almacenarse directamente en este tipo de memo.
La solución consiste en convertir el UUID a sus 16 bytes binarios (UUID.bytes) y completar el resto con ceros hasta alcanzar 32 bytes. 
Ese valor se envía utilizando un MemoHash, mediante TransactionBuilder.add_hash_memo(...).

2. ¿Cuándo usar Payment y cuándo CreateAccount?
Aquí existe una diferencia importante entre XRPL y Stellar.
En XRPL una operación Payment puede crear automáticamente una cuenta si aún no existe una y el pago cubre la reserva mínima.
En Stellar el comportamiento es diferente, si la cuenta destino no existe, una operación Payment falla inmediatamente con el error op_no_destination.
Por eso, antes de enviar un pago es necesario consultar la Horizon API para verificar si la cuenta destino ya existe en el ledger.
Si la cuenta existe, se utiliza la operación Payment.
Si la cuenta no existe, se debe usar CreateAccount, enviando al menos 1 XLM, que es el mínimo necesario para activar la cuenta.

3. Manejo de montos y decimales
Stellar trabaja con 7 decimales, mientras que XRPL utiliza 6 decimales (drops).
Para evitar problemas de precisión causados por los números de punto flotante, los montos siempre deben enviarse como cadenas de texto, por ejemplo:
"10.0000000"
y nunca como valores float.

4. Cambios en la API (stellar-sdk >= 15.0.0)
En las versiones actuales de stellar-sdk, el método TransactionBuilder.append_payment_op(...) recibe un objeto Asset en el parámetro asset (por ejemplo, Asset.native()).
El parámetro asset_code pertenecía a la antigua biblioteca stellar_base.builder.Builder y ya no forma parte de la API moderna.

De forma similar, los memos de tipo hash se agregan con:
add_hash_memo(...)

y no con:
add_memo_hash(...)

===============================================================================
"""

import sys
import uuid
import requests
from decimal import Decimal

try:
    from stellar_sdk import Server, Keypair, Network, TransactionBuilder, Asset
    from stellar_sdk.strkey import StrKey
    from stellar_sdk.exceptions import BadRequestError, NotFoundError
except ImportError:
    print("[ERROR] La librería 'stellar-sdk' no está instalada.")
    print("Por favor instala las dependencias ejecutando: pip install 'stellar-sdk>=15.0.0'")
    sys.exit(1)

# Configuración de Testnet
HORIZON_URL = "https://horizon-testnet.stellar.org"
FRIENDBOT_URL = "https://friendbot.stellar.org"
PASSPHRASE = Network.TESTNET_NETWORK_PASSPHRASE
EXPLORER_BASE_URL = "https://stellar.expert/explorer/testnet/tx/"

# Código de error de Horizon que se espera al pagar a una cuenta inexistente.
OP_NO_DESTINATION = "op_no_destination"

server = Server(horizon_url=HORIZON_URL)


def create_and_fund_account(name: str) -> Keypair:
    # Crea un nuevo Keypair e inyecta fondos con Friendbot.
    kp = Keypair.random()
    print(f"  > Generando {name}: {kp.public_key}")
    try:
        resp = requests.get(f"{FRIENDBOT_URL}?addr={kp.public_key}", timeout=10)
        if resp.status_code == 200:
            print(f"  > {name} fondeada exitosamente.")
        else:
            print(f"  > [ERROR] Friendbot devolvió status {resp.status_code}")
            sys.exit(1)
    except requests.RequestException as e:
        print(f"[ERROR CONEXIÓN] No se pudo conectar a Friendbot/Horizon: {e}")
        print("Saliendo..")
        sys.exit(0)
    return kp


def get_balance(public_key: str) -> str:
    # Obtiene el saldo nativo (XLM) de una cuenta.
    try:
        acc = server.accounts().account_id(public_key).call()
        for balance in acc.get("balances", []):
            if balance.get("asset_type") == "native":
                return balance.get("balance", "0")
    except Exception as e:
        print(f"[ERROR] No se pudo obtener el saldo de {public_key}: {e}")
    return "0"


def derive_memo_hash_from_uetr(uetr_str: str) -> bytes:
    # Convierte un UETR (UUID de 36 chars) a un MemoHash de 32 bytes.
    uetr_uuid = uuid.UUID(uetr_str)
    raw_16_bytes = uetr_uuid.bytes
    # Rellenar con ceros a la derecha para completar los 32 bytes
    memo_hash_32 = raw_16_bytes.ljust(32, b"\x00")
    return memo_hash_32


def extract_result_codes(error: BadRequestError) -> list:
    """
    Extrae los códigos de resultado (ej. 'op_no_destination') de la respuesta
    de error de Horizon, sin asumir su forma. Devuelve una lista de strings.
    """
    codes = []
    try:
        extras = (error.extras or {}) if hasattr(error, "extras") else {}
        result_codes = extras.get("result_codes", {})
        if isinstance(result_codes, dict):
            tx_code = result_codes.get("transaction")
            if tx_code:
                codes.append(tx_code)
            op_codes = result_codes.get("operations") or []
            codes.extend(op_codes)
    except Exception:
        pass
    return codes


def main():
    print("================================================")
    print("SPIKE STELLAR TESTNET (Ola 0 - S0.1 / XLM-01)")
    print("================================================")

    # 1. Crear y fondear cuentas A y B

    print("\n[PASO 1] Creando dos cuentas de prueba en Testnet..")
    account_a = create_and_fund_account("Cuenta A (Remitente)")
    account_b = create_and_fund_account("Cuenta B (Destinatario)")

    balance_a = get_balance(account_a.public_key)
    balance_b = get_balance(account_b.public_key)

    print(f"  - Saldo Cuenta A: {balance_a} XLM")
    print(f"  - Saldo Cuenta B: {balance_b} XLM")

    # 2. Pago de 10 XLM de A a B con MemoHash derivado de UETR

    test_uetr = str(uuid.uuid4())
    print(f"\n[PASO 2] Ejecutando Pago de 10 XLM de A a B con MemoHash..")
    print(f"  - UETR generado (36 chars): {test_uetr}")

    memo_hash_bytes = derive_memo_hash_from_uetr(test_uetr)
    print(f"  - Bytes de MemoHash (32 bytes): {memo_hash_bytes.hex()}")

    try:
        source_account = server.load_account(account_a.public_key)
        tx = (
            TransactionBuilder(
                source_account=source_account,
                network_passphrase=PASSPHRASE,
                base_fee=100,
            )
            .append_payment_op(
                destination=account_b.public_key,
                amount="10.0000000",
                asset=Asset.native(),
            )
            .add_hash_memo(memo_hash_bytes)
            .set_timeout(30)
            .build()
        )

        tx.sign(account_a)
        response = server.submit_transaction(tx)
        tx_hash = response["hash"]

        print(f"  > Pago exitoso!")
        print(f"  > Hash TX: {tx_hash}")
        print(f"  > Explorador: {EXPLORER_BASE_URL}{tx_hash}")
        print(f"  > Nuevo saldo B: {get_balance(account_b.public_key)} XLM")

    except (requests.RequestException, ConnectionError) as e:
        print(f"[ERROR CONEXIÓN] No se pudo conectar a Horizon: {e}")
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] Error al procesar pago: {e}")
        sys.exit(1)

    # 3. Pago a una cuenta inexistente (Confirmar op_no_destination y CreateAccount)

    print("\n[PASO 3] Probando pago hacia una cuenta inexistente..")
    unused_keypair = Keypair.random()
    print(f"  - Cuenta inexistente de prueba: {unused_keypair.public_key}")

    # INTENTO 1: Usar Payment (Debe fallar específicamente con op_no_destination)
    print("  > Intentando Payment convencional (se espera que falle)..")
    try:
        source_account = server.load_account(account_a.public_key)
        tx_fail = (
            TransactionBuilder(
                source_account=source_account,
                network_passphrase=PASSPHRASE,
                base_fee=100,
            )
            .append_payment_op(
                destination=unused_keypair.public_key,
                amount="1.0000000",
                asset=Asset.native(),
            )
            .set_timeout(30)
            .build()
        )
        tx_fail.sign(account_a)
        server.submit_transaction(tx_fail)
        print("  > [ERROR INESPERADO] El pago a la cuenta inexistente debió haber fallado.")
        sys.exit(1)
    except BadRequestError as e:
        codes = extract_result_codes(e)
        if OP_NO_DESTINATION in codes:
            print(f"  > [CONFIRMADO] Falló con el código esperado: {OP_NO_DESTINATION}")
        else:
            print(f"  > [ERROR INESPERADO] Falló, pero NO con '{OP_NO_DESTINATION}'.")
            print(f"  > Códigos recibidos: {codes}")
            sys.exit(1)
    except (requests.RequestException, ConnectionError) as e:
        print(f"[ERROR CONEXIÓN] No se pudo conectar a Horizon: {e}")
        sys.exit(0)

    # INTENTO 2: Usar CreateAccount (Debe ser exitoso)
    print("  > Intentando CreateAccount con 1 XLM..")
    try:
        source_account = server.load_account(account_a.public_key)
        tx_create = (
            TransactionBuilder(
                source_account=source_account,
                network_passphrase=PASSPHRASE,
                base_fee=100,
            )
            .append_create_account_op(
                destination=unused_keypair.public_key,
                starting_balance="1.0000000",
            )
            .set_timeout(30)
            .build()
        )
        tx_create.sign(account_a)
        resp_create = server.submit_transaction(tx_create)
        create_hash = resp_create["hash"]

        print(f"  > CreateAccount exitoso!")
        print(f"  > Hash TX: {create_hash}")
        print(f"  > Explorador: {EXPLORER_BASE_URL}{create_hash}")
        print(f"  > Cuenta activada con saldo: {get_balance(unused_keypair.public_key)} XLM")

    except (requests.RequestException, ConnectionError) as e:
        print(f"[ERROR CONEXIÓN] No se pudo conectar a Horizon: {e}")
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] Error al crear cuenta: {e}")
        sys.exit(1)

    # 4. Validación de direcciones con StrKey

    print("\n[PASO 4] Validando direcciones con StrKey..")

    valid_stellar_addr = account_a.public_key
    xrpl_addr = "rPT1S237JH9M2LW9G7ain2zUee7B6C7P"
    corrupt_stellar_addr = valid_stellar_addr[:-4] + "XXXX"

    is_valid_stellar = StrKey.is_valid_ed25519_public_key(valid_stellar_addr)
    is_valid_xrpl = StrKey.is_valid_ed25519_public_key(xrpl_addr)
    is_valid_corrupt = StrKey.is_valid_ed25519_public_key(corrupt_stellar_addr)

    print(f"  - Dirección Stellar válida ('{valid_stellar_addr[:10]}..'): {is_valid_stellar}")
    print(f"  - Dirección XRPL ('{xrpl_addr}'): {is_valid_xrpl}")
    print(f"  - Dirección Stellar con checksum corrupto: {is_valid_corrupt}")

    assert is_valid_stellar is True, "La dirección válida debería retornar True"
    assert is_valid_xrpl is False, "La dirección XRPL debería ser rechazada (False)"
    assert is_valid_corrupt is False, "La dirección corrupta debería ser rechazada (False)"

    print("\n===================================================")
    print("El spike finalizó con todas las pruebas en verde")
    print("===================================================")


if __name__ == "__main__":
    main()