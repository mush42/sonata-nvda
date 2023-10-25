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

After downloading a voice, go to NVDA settings, and choose `Piper` category, and then click the button labled `Install from file`. Choose the file you downloaded, wait for the voice to install, and restart NVDA to refresh the voices list.

## A note on voice quality

The currently available voices are trained using freely available TTS datasets, which are generally of low quality (mostly public domain audio books or research quality recordings).

Additionally, these datasets are not comprehensive, hence some voices may exhibit incorrect or weird pronunciation. Both issues could be resolved by using better datasets for training.

Luckily, the `Piper` developer and some developers from the blind and vision-impaired community are working on training better voices.

# A note on add-on's performance

The current release is a technical preview. Soon enough the add-on will be rewritten in `Rust`, a programming language that provides better performance than `Python`.

# License

Copyright(c) 2023, Musharraf Omer. This software is licensed under The GNU GENERAL PUBLIC LICENSE Version 2 (GPL v2).
