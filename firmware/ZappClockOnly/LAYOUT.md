# Layout do Zapp Clock - Fase 1

Tela usada pelo projeto: TFT ST7735 em modo paisagem, aproximadamente **160 x 128 pixels**.

## Fluxo desejado

1. A primeira imagem que aparece na tela deve ser o relógio.
2. Depois o relógio apaga.
3. Entra uma tela de carregamento do Wi-Fi.
4. Essa tela mostra um ícone rodando enquanto o Wi-Fi carrega.
5. Quando o Wi-Fi sincronizar a hora, volta para o relógio atualizado.

---

# Layout principal do relógio

Pedido do Davi:

- No **canto superior esquerdo**: face do Zapp usando estilo/RobotEyes.
- **Acima do centro**: nome `ZAPP`.
- No **centro**: hora e minuto grandes.
- À **direita do centro**: segundos pequenininhos.
- À **esquerda do centro**: dia de hoje, mês e ano.
- No **canto inferior esquerdo**: clima e temperatura.
- **Abaixo do centro**: espaço reservado para outra coisa que Davi ainda vai definir.

## Rascunho visual

```text
+------------------------------------------------+
| Zapp face        ZAPP                          |
|  RobotEyes                                     |
|                                                |
|  06/06/2026      12:34   56                    |
|                                                |
|                  [ espaço reservado ]          |
|                                                |
|  clima  28C                                    |
+------------------------------------------------+
```

## Mapa de áreas aproximado

A tela tem largura 160 e altura 128.

```text
x=0                                            x=159
+------------------------------------------------+ y=0
| face 0-42       nome ZAPP 55-105               |
| y 0-32                                        |
|                                                |
| data 4-48       hora 58-124     seg 130-154    |
| y 48-76                                       |
|                                                |
| reservado abaixo do centro 45-150              |
| y 82-105                                      |
|                                                |
| clima/temp 4-70                                |
+------------------------------------------------+ y=127
```

## Coordenadas propostas

### 1. Face do Zapp / RobotEyes

- Área: `x = 2 até 42`, `y = 2 até 34`.
- Face pequena, para não brigar com o relógio.
- Como o RobotEyes completo costuma usar bastante tela, talvez seja melhor desenhar uma **mini face inspirada no RobotEyes**, com dois olhos cianos/preenchidos, em vez de iniciar a biblioteca RobotEyes na tela toda.

### 2. Nome ZAPP

- Texto: `ZAPP`.
- Posição: centro horizontal aproximado, `y = 6`.
- Tamanho: `2`, se couber bem.
- Cor: ciano.

### 3. Hora e minuto

- Formato: `HH:MM`.
- Posição: centro da tela.
- Coordenada aproximada: `x = 58`, `y = 48`.
- Tamanho: `3`.
- Cor: verde.

### 4. Segundos pequenos

- Formato: `SS`.
- Posição: lado direito da hora.
- Coordenada aproximada: `x = 134`, `y = 56`.
- Tamanho: `1` ou `2`.
- Cor: amarelo ou verde claro.

### 5. Data no lado esquerdo do centro

- Formato: `DD/MM/YYYY`.
- Posição: lado esquerdo da hora.
- Coordenada aproximada: `x = 4`, `y = 54`.
- Tamanho: `1`.
- Cor: branco.

Se ficar apertado, alternativa mais compacta:

- linha 1: `06/06`
- linha 2: `2026`

### 6. Clima e temperatura

- Posição: canto inferior esquerdo.
- Coordenada aproximada: `x = 4`, `y = 112`.
- Exemplo: `Sol 28C` ou `Chuva 26C`.
- Tamanho: `1`.
- Cor: amarelo/branco/ciano dependendo do clima.

Observação: nesta fase, o clima ainda pode ficar como espaço reservado ou texto `Clima --C`, porque Davi pediu para começar validando o relógio primeiro.

### 7. Espaço abaixo do centro

- Área reservada: `x = 45 até 150`, `y = 82 até 105`.
- Conteúdo: Davi ainda vai definir.
- Por enquanto no código pode aparecer vazio ou uma linha discreta tipo `---` apenas para testar alinhamento.

---

# Tela de carregamento Wi-Fi

Depois da primeira tela de relógio, o relógio apaga e aparece o carregamento.

## Rascunho

```text
+------------------------------------------------+
|                    ZAPP                        |
|                                                |
|                 conectando                     |
|                    WiFi                        |
|                                                |
|                 bolinha girando                |
|                                                |
|              procurando rede salva             |
+------------------------------------------------+
```

## Animação proposta

Desenhar um círculo imaginário no centro:

- centro: `x = 80`, `y = 68`
- raio: `14`
- uma bolinha ciano/amarela gira ao redor.

Essa opção combina mais com tela de robô do que usar caracteres `| / - \\`.

---

# Próximos passos de implementação

1. Criar função `drawMiniZappFace()` para a face no canto superior esquerdo.
2. Criar função `drawClockLayout()` para desenhar as áreas fixas.
3. Criar função `updateClockValues()` para atualizar só os números, sem redesenhar a tela inteira.
4. Criar função `showWifiLoadingScreen()` com bolinha girando.
5. Ajustar o fluxo:
   - mostrar relógio primeiro;
   - apagar;
   - carregar Wi-Fi com animação;
   - voltar ao relógio sincronizado.
