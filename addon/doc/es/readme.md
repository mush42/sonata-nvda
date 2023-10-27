# Voces neuronales Piper para NVDA

Este complemento implementa un controlador de sintetizador de voz para NVDA usando [Piper](https://github.com/rhasspy/piper).

[Piper](https://github.com/rhasspy/piper) es un sistema de texto a voz rápido, local y neuronal que suena bien y está optimizado para funcionar en dispositivos de gama baja, tales como Raspberry Pi.

Puedes escuchar las muestras de voz aquí: [Piper voice samples](https://rhasspy.github.io/piper-samples/).

Este complemento usa la [implementación de piper en rust](https://github.com/mush42/piper-rs) la cual está siendo desarrollada por Musharraf Omer.


# Instalación

## Descargando el complemento

Puedes encontrar el paquete de complemento dentro de la sección assets de la [página de lanzamiento](https://github.com/mush42/piper-nvda/releases/latest)

## Agregando voces

El complemento es solo un controlador, por lo que no viene con voces por defecto. Necesitarías descargar e instalar las voces que quieras de forma manual.

Tras instalar el complemento y reiniciar NVDA, el complemento te pedirá que descargues e instales al menos una voz, por lo que te dará la opción de abrir la página web de descarga de voces.

También puedes abrir la página de descarga de voces desde la categoría `Piper` en las opciones de NVDA.

Cada voz está disponible como un archivo `.tar.gz`, que es un formato de archivo similar a los archivos `.zip` y `.rar`. El archivo contiene el modelo de voz y sus configuraciones.

Ten en cuenta que te recomendamos seleccionar las voces con la calidad  `low` o `x-low` para tu(s) idioma(s) de destino, ya que estas proporcionan un mejor rendimiento.

Después de descargar una voz, ve a las opciones de NVDA, y selecciona la categoría `Piper`, y luego haz clic en el botón etiquetado como `Instalar desde un archivo local`. Selecciona el archivo que descargaste, espera a que la voz se instale, y reinicia NVDA para refrescar la lista de voces.

## Una nota acerca de la calidad de la voz

Las voces actualmente disponibles están entrenadas usando conjuntos de datos para TTS gratuitos que, generalmente, son de baja calidad (en su mayoría audiolibros bajo dominio público o grabaciones de calidad para investigación).

Agregando que, estos conjuntos de datos no son precisos, por lo que algunas voces pueden presentar una pronunciación incorrecta o extraña. Ambos problemas podrían resolverse utilizando mejores conjuntos de datos para el entrenamiento.

Con suerte, el desarrollador de `Piper` y algunos desarrolladores de la comunidad de personas ciegas y deficiencia visual están trabajando en entrenar mejores voces.

# Licencia

Copyright(c) 2023, Musharraf Omer. Este software está licenciado bajo la GNU GENERAL PUBLIC LICENSE Version 2 (GPL v2).
