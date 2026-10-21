# Ensamblador RV32I

Traduce un programa en ensamblador RV32I con sintaxis GNU a una imagen hexadecimal de la sección `.text` y, opcionalmente, de la sección `.data`.

## Uso

```sh
python assembler.py programa.asm programa.hex [programa.data.hex]
```

- `programa.asm`: el fuente, en UTF-8 (se acepta BOM y saltos de línea CRLF).
- `programa.hex`: la imagen de `.text`, que empieza en `0x00000000`.
- `programa.data.hex` (opcional): la imagen de `.data`, que empieza en `0x10000000`. Si no se nombra, los datos se ensamblan y se validan, pero no se escriben.

Cada línea de salida es una palabra de 32 bits: 8 dígitos hexadecimales en minúscula, sin prefijo, terminada en `\n`. La línea 1 es la palabra de la dirección base, la línea 2 la siguiente, y así. Los bytes se agrupan de 4 en 4 en little-endian; si al final sobran bytes se rellena con ceros. Si una sección quedó vacía, su archivo se crea con 0 bytes.

Códigos de salida:

| código | significado |
|---|---|
| 0 | ensamblado sin errores; se escribieron las salidas |
| 1 | errores de ensamblado |
| 2 | error de uso o de E/S: número de argumentos incorrecto, entrada ilegible o que no es UTF-8, salida igual a la entrada, salida que no se puede escribir o borrar |

Con errores de ensamblado se imprimen todos en stderr, ordenados por línea, con el formato `archivo:línea: error: mensaje`, donde `archivo` es la ruta tal como se escribió en la línea de comandos. No se escribe ninguna salida y, si los archivos de salida nombrados ya existían de una ejecución anterior, se borran, para que no quede un `.hex` viejo que parezca el resultado del fuente actual.

## Dependencias

- En ejecución: ninguna. Solo Python 3.12 o posterior y su biblioteca estándar.
- Para desarrollo (opcional): `mypy`, para la verificación de tipos.
- Docker, solo para regenerar los resultados esperados de `tests/ok` con GNU as. Desde la raíz del repositorio:

```sh
docker build -t rv32i-gnu -f tests/Dockerfile tests
docker run --rm -v "$PWD:/w" -w /w --user "$(id -u):$(id -g)" rv32i-gnu sh tests/regen.sh
```

## Pruebas

```sh
python -m unittest discover -s tests -t . -v
```

- `tests/test_*.py`: un archivo de pruebas por módulo (`lexer`, `parser`, `semantic`, `codegen`, `isa`, `model`, `cli`), más `test_typing.py`, que revisa la regla de tipado explícito, y `test_golden.py`.
- `tests/ok/`: programas correctos. Cada `.asm` viene con el `.hex` (y el `.data.hex` si tiene datos) que produce GNU as 2.44 (`riscv64-unknown-elf-as -march=rv32i -mabi=ilp32 -mno-relax` y luego `ld` con `.text` en 0 y `.data` en `0x10000000`). `test_ok` exige que la salida del ensamblador sea idéntica en texto. Los esperados se regeneran con los dos comandos de Docker de la sección anterior (`tests/regen.sh` recorre `tests/ok/*.asm`).
- `tests/err/`: programas con errores. Cada `.asm` viene con un `.expect` de una línea por error esperado, `N:palabra clave`. `test_err` primero valida el `.expect`: toda línea debe tener la forma `N:palabra clave`, con la palabra empezando por un carácter que no sea espacio. Luego ensambla una copia del `.asm` en un directorio temporal y exige código 1, que el temporal siga conteniendo solo el `.asm` (no se crea ninguna salida), que toda línea no vacía de stderr sea un diagnóstico `archivo:N: error: mensaje`, que cada línea `N` tenga exactamente tantos diagnósticos como entradas suyas en el `.expect`, cada palabra clave contenida en alguno de ellos, y que no haya diagnósticos en otras líneas. Estos esperados se escriben a mano: GNU no sirve de oráculo porque sus mensajes son otros (en inglés y con otro texto), y en algunos casos acepta lo que este ensamblador rechaza a propósito (ver "Decisiones documentadas").

## Diseño

### Fases y pasadas

Es un compilador en miniatura de cinco fases y dos pasadas sobre el fuente:

1. **Léxico** (`rvasm/lexer.py`, `tokenize`): parte cada línea en `Token` (identificador, número, cadena, coma, dos puntos, paréntesis). `parse_num` convierte números decimales, `0x` y `0b`.
2. **Sintaxis** (`rvasm/parser.py`, `parse`): produce una `Statement` por línea: etiquetas, mnemónico o directiva y operandos (`Operand` de tipo `reg`, `num`, `sym`, `mem` o `str`). No conoce las firmas de las instrucciones: un identificador es `reg` si está en `REGISTERS` y `sym` si no.
3. **Semántica, pasada 1** (`rvasm/semantic.py`, `analyze`): comprueba operandos y rangos de las constantes, expande las pseudoinstrucciones a instrucciones base, asigna direcciones, llena la tabla de símbolos y emite los bytes de `.data`.
4. **Generación, pasada 2** (`rvasm/codegen.py`, `generate`): resuelve las etiquetas, valida las distancias que dependen de ellas y codifica cada instrucción con los codificadores de `rvasm/isa.py`.
5. **Emisión** (`rvasm/cli.py`, `main`): ordena los diagnósticos, empaqueta los bytes en palabras (`pack_words`) y escribe los archivos solo si no hubo errores.

`assembler.py` solo llama a `rvasm.cli.main`. Las tablas de la ISA (`SPEC`, `SIGNATURES`, `PSEUDOS`, `RANGES`, `ENCODERS`, `REGISTERS`) están en `rvasm/isa.py` y los tipos compartidos en `rvasm/model.py`.

### Representación de una instrucción

- `Spec` (en `isa.py`): lo fijo de cada mnemónico base: formato (`R`, `I`, `S`, `B`, `U`, `J`), `opcode`, `funct3`, `funct7` y la forma de sus operandos.
- `Instr` (en `model.py`): una instrucción base concreta, ya expandida: línea del fuente, mnemónico, `rd`, `rs1`, `rs2`, `imm`, dirección y, si depende de una etiqueta, un `Reloc`.
- `Reloc`: qué falta por resolver en la pasada 2: el tipo (`pcrel`, `hi` o `lo`), la etiqueta y el `anchor`, la dirección desde la que se mide la distancia.

Una pseudoinstrucción se convierte en la pasada 1 en una o dos `Instr`; la pasada 2 nunca ve pseudoinstrucciones.

### Resolución de etiquetas

- Cada sección tiene su contador: `.text` arranca en `0x00000000` y `.data` en `0x10000000`. Las secciones se pueden alternar y cada contador sigue donde quedó.
- Hay una sola tabla de símbolos (`Unit.symtab`) para ambas secciones. Una etiqueta toma el valor del contador de la sección activa en su línea.
- El tamaño de cada sentencia se conoce al leer su línea, así que dos pasadas bastan: la primera fija todas las direcciones y la segunda ya tiene la tabla completa.
- Un `Reloc` se resuelve como `etiqueta − anchor`:
  - `pcrel` (ramas y `jal`): el `anchor` es la propia instrucción y la distancia se valida contra el rango del formato.
  - `hi` y `lo` (el `auipc` y la instrucción que lo sigue en `la`, `call`, `tail` y en cargas y almacenamientos con etiqueta): ambos usan como `anchor` la dirección del `auipc`, y la distancia se parte con `hi_lo`.
- Un `.word etiqueta` en `.data` se guarda como `Fixup` y se rellena en la pasada 2.

### Política de errores

1. **No se detiene en el primer error.** Cada línea se procesa aunque las anteriores hayan fallado, y se informan todos los errores, ordenados por línea.
2. **Un error por paso y por línea.** En cada línea primero se registran las etiquetas y luego se procesa la instrucción o directiva; en cada paso gana el primer error. Una etiqueta duplicada no impide registrar las demás de la línea.
3. **La pasada 1 valida lo constante; la pasada 2, lo que depende de etiquetas.** Rangos de inmediatos, registros, número y tipo de operandos se revisan en la semántica, salvo el registro base de un acceso a memoria (`0(x40)`), que lo rechaza ya el parser; etiquetas no definidas y distancias de ramas y saltos, en la generación.
4. **Las direcciones de `.text` se conservan aunque haya errores.** Si una instrucción falla pero su tamaño se conoce, el contador de `.text` avanza igual. Si no se conoce (línea que no parseó, mnemónico inexistente o `li` con inmediato inválido), `Unit.layout_ok` pasa a `False` y la pasada 2 deja de informar errores de rango, que serían falsos; las etiquetas no definidas se informan siempre. En `.data` no hay reserva: una directiva de datos con error no avanza el contador de `.data` desde el valor erróneo en adelante (los valores anteriores de la misma línea sí cuentan).

### Tipado explícito

Todo el código, pruebas incluidas, está anotado: cada parámetro y retorno, cada asignación (`pc: int = 0`), las variables de `for` y `with` declaradas en la línea anterior, constantes con `Final` y alias con `TypeAlias`. Están prohibidos la asignación sin anotación, el desempaquetado (`a, b = f()`, `for k, v in ...`), las lambdas, el operador walrus y `Any`.

Se verifica de dos formas, y ambas deben pasar:

- `mypy` en modo `strict`, con `disallow_any_explicit` y `disallow_any_unimported` (configuración en `pyproject.toml`): `.venv/bin/mypy`.
- `tests/test_typing.py`, que recorre el AST de todos los `.py` del repositorio y falla si encuentra alguna de las formas prohibidas.

### Pruebas en patrón AAA

Cada método de prueba tiene tres secciones marcadas con los comentarios `# Arrange`, `# Act` y `# Assert`, en ese orden. Cuando una prueba recorre casos con `subTest`, la tabla de casos va en `# Arrange` y `# Act` y `# Assert` van dentro de cada `subTest`. Esta regla no la comprueba ninguna herramienta: se revisa a mano en cada prueba nueva.

## Por qué `li`, `la` y `call` ocupan dos instrucciones y por qué se suma `0x800`

*Borrador técnico: el autor debe reescribir este apartado con sus palabras antes de entregar.*

Una instrucción RV32I mide 32 bits, y de ellos solo 12 pueden ser un inmediato en las instrucciones tipo I (`addi`, `jalr`, cargas) y 20 en las tipo U (`lui`, `auipc`). Un valor o una dirección arbitraria de 32 bits no cabe en una sola instrucción, así que se arma en dos:

- `li rd, v`: el inmediato se interpreta primero como un valor de 32 bits con signo (`to_signed32`), así que `0xFFFFFFFF` es −1 y sale en un solo `addi rd, x0, -1`. Si `v` cabe en 12 bits con signo (`[-2048, 2047]`) basta `addi rd, x0, v`. Si no, `lui rd, hi` carga los 20 bits altos y `addi rd, rd, lo` suma los 12 bajos. Si `lo` resulta 0, se omite el `addi`.
- `la rd, etiqueta`: igual, pero relativo al PC, para que el programa no dependa de dónde se cargue: `auipc rd, hi` suma los bits altos de la distancia al PC y `addi rd, rd, lo` suma los bajos.
- `call etiqueta`: `jal` solo alcanza ±1 MiB, así que se usa `auipc ra, hi` y `jalr ra, lo(ra)`, que alcanza cualquier dirección de 32 bits. `tail` hace lo mismo con `t1` y sin guardar el retorno.

El problema está en que `addi` (y `jalr`) **extiende el signo** de sus 12 bits: si el bit 11 de `lo` es 1, el procesador lo interpreta como negativo y le resta `0x1000` al resultado. Para compensar, cuando eso pasa hay que sumar 1 a `hi`. Sumar `0x800` antes de tomar los bits altos hace exactamente eso: si el bit 11 está encendido, la suma acarrea un 1 hacia el bit 12. En el código es `hi_lo` en `rvasm/isa.py`:

```
hi = ((v + 0x800) >> 12) & 0xFFFFF
lo = ((v + 0x800) & 0xFFF) - 0x800
```

Ejemplo con `li a0, 0x12345FFF`:

- Sin el ajuste: `hi = 0x12345`, `lo = 0xFFF`. Pero `0xFFF` en 12 bits con signo es −1, así que `lui` + `addi` dan `0x12345000 − 1 = 0x12344FFF`. Incorrecto.
- Con el ajuste: `0x12345FFF + 0x800 = 0x123467FF`, de donde `hi = 0x12346` y `lo = 0x7FF − 0x800 = −1`. Entonces `lui a0, 0x12346` y `addi a0, a0, -1` dan `0x12346000 − 1 = 0x12345FFF`. Correcto.

## Decisiones documentadas

- **Cero inicial rechazado.** `010` o `08` dan `inmediato inválido`: en GNU un cero inicial significa octal, y aceptarlo como decimal daría otro valor sin avisar. Se admiten decimal, `0x` y `0b`, con signo opcional.
- **`.globl` ignorado.** `.globl` y `.global` se aceptan y no hacen nada, porque hay un solo archivo y no se enlaza; se aceptan para que los programas copiados que los traen ensamblen. Cualquier otra directiva fuera de `.text`, `.data`, `.word`, `.half`, `.byte` y `.string` es `directiva desconocida`.
- **Mayúsculas.** Mnemónicos y directivas no distinguen mayúsculas (`ADDI`, `.TEXT`); registros y etiquetas sí (`A0` no es un registro).
- **Borrado de salidas viejas.** Con errores de ensamblado se borran los archivos de salida nombrados que ya existían. Si una salida es el mismo archivo que la entrada, se rechaza con código 2 sin tocar nada. Lo mismo si el `.hex` y el `.data.hex` resuelven al mismo archivo: `las salidas 'a' y 'b' son el mismo archivo`, código 2 y ningún archivo tocado. Si falla escribir el `.data.hex`, se borra el `.hex` recién escrito, para no dejar una salida a medias.
- **Entrada no UTF-8.** Un `.asm` que no es UTF-8 válido es un error de E/S (código 2), no de ensamblado.
- **`li x0` según el enunciado.** `li` ocupa 4 u 8 bytes solo según el valor, también cuando `rd` es `x0`, tal como lo describe el enunciado. Medido: para `li x0, 0x12345000` GNU emite `lui zero` + `addi zero, zero, 0` (8 bytes) y este ensamblador emite solo el `lui` (4 bytes), siguiendo la regla del enunciado. Por eso ese caso no está en `tests/ok`.
- **Sin alineación en `.data`.** Cada dato va justo después del anterior: un `.word` después de `.string "hi"` queda en una dirección no múltiplo de 4.
- **Etiquetas con nombre de registro.** Una etiqueta como `t1:` o `a0:` se puede definir, pero no usar como destino: el parser clasifica `t1` como registro y la semántica informa `debe ser una etiqueta, se encontró el registro 'x6'`. GNU sí lo acepta.
- **Mnemónico en los mensajes.** Los errores de operandos de la pasada 1 nombran el mnemónico tal como se escribió (`'j'`, `'beqz'`); los de distancia de la pasada 2 nombran la instrucción ya expandida (`j` aparece como `'jal'`, `beqz` como `'beq'`).
- **Registros normalizados en los mensajes.** Los mensajes nombran los registros por su número, no por el nombre escrito: `.word a0` informa `se encontró el registro 'x10'` y `8(sp)` aparece como `'8(x2)'`.
- **Operandos numéricos en los mensajes.** Un operando numérico se describe como "el inmediato N", por ejemplo `debe ser una etiqueta, se encontró el inmediato 8`.
