# Voces neuronales Sonata para NVDA

Este complemento implementa un controlador de sintetizador de voz para NVDA usando modelos neuronales de texto a voz. Soporta [Piper](https://github.com/rhasspy/piper).

[Piper](https://github.com/rhasspy/piper) es un sistema de texto a voz rápido, local y neuronal que suena bien y está optimizado para funcionar en dispositivos de gama baja, tales como Raspberry Pi.

Puedes escuchar las muestras de voz aquí: [Piper voice samples](https://rhasspy.github.io/piper-samples/).

Este complemento usa [Sonata: un motor de Rust multiplataforma para modelos de texto a voz neuronales](https://github.com/mush42/sonata) la cual está siendo desarrollada por Musharraf Omer.


# Instalación

## Descargando el complemento

Puedes encontrar el paquete de complemento dentro de la sección assets de la [página de lanzamientos o releases](https://github.com/mush42/sonata-nvda/releases/latest)

## Agregando voces

El complemento es solo un controlador, por lo que no viene con voces por defecto. Necesitarías descargar e instalar las voces que quieras de forma manual.

Tras instalar el complemento y reiniciar NVDA, el complemento te pedirá que descargues e instales al menos una voz, por lo que te dará la opción de abrir el administrador de voces.

También puedes abrir el administrador de voces desde el menú principal de NVDA.

Ten en cuenta que te recomendamos seleccionar voces con la calidad  `low (baja)` o `medium (estándar)` para tu(s) idioma(s) de destino, ya que estas proporcionan un mejor rendimiento. Para un rendimiento adicional, puedes considerar descargar la variante `rápida` de una voz a un costo de una calidad de habla ligeramente baja.

También puedes instalar voces desde archivos locales. Después de obtener el archivo de una voz, abre el administrador de voces, en la pestaña de voces instaladas, pulsa el botón etiquedado como `Instalar desde un archivo local`. Selecciona el archivo de la voz, espera a que esta se instale, y reinicia NVDA para refrescar la lista de voces.

## Una nota acerca de la calidad de la voz

Las voces actualmente disponibles están entrenadas usando conjuntos de datos para TTS gratuitos que, generalmente, son de baja calidad (en su mayoría audiolibros bajo dominio público o grabaciones de calidad para investigación).

Agregando que, estos conjuntos de datos no son precisos, por lo que algunas voces pueden presentar una pronunciación incorrecta o extraña. Ambos problemas podrían resolverse utilizando mejores conjuntos de datos para el entrenamiento.

Con suerte, el desarrollador de `Piper` y algunos desarrolladores de la comunidad de personas ciegas y deficiencia visual están trabajando en entrenar mejores voces.

# Licencia

Copyright(c) 2024, Musharraf Omer. Este software está licenciado bajo la GNU GENERAL PUBLIC LICENSE, Versión 2 (GPL v2).
