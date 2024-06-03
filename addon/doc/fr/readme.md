# Voix neuronales Sonata pour NVDA

Cette extension implémente un pilote de synthèse vocale pour NVDA utilisant  le modèles neuronaux TTS. Elle supporte [Piper](https://github.com/rhasspy/piper).

[Piper](https://github.com/rhasspy/piper) est un système de synthèse de texte à parole rapide, local et neuronal qui sonne bien et est optimisé pour fonctionner sur des appareils bas de gamme tels que le Raspberry Pi.

Vous pouvez écouter les extraits de voix de Piper ici : [Piper voice samples](https://rhasspy.github.io/piper-samples/).

Cette extension utilise [Sonata : Un moteur Rust multiplateforme pour les modèles neuronaux TTS](https://github.com/mush42/ssonata) qui est développé par Musharraf Omer.


# Installation

## Téléchargement de l'extension

Vous pouvez trouver le package de l'extension sous la section assets à partir de la [page release](https://github.com/mush42/sonata-nvda/releases/latest)

## Ajout de voix

L'extension n'est qu'un pilote, elle est livrée sans aucune voix par défaut. Vous devez télécharger et installer les voix souhaitées à partir du gestionnaire de voix.

Lors de l'installation de l'extension et du redémarrage de NVDA, l'extension vous demandera de télécharger et d'installer au moins une voix, et vous donnera la possibilité d'ouvrir le gestionnaire de voix.

Vous pouvez également ouvrir le gestionnaire de voix depuis le menu principal de NVDA.

Veuillez noter que nous vous recommandons de choisir des voix de qualité `basse` ou `moyenne` pour votre ou vos langues cibles, car elles offrent généralement une meilleure réactivité. Pour plus de réactivité, vous pouvez choisir de télécharger la variante `rapide` d'une voix au prix d'une qualité vocale légèrement inférieure.

Vous pouvez également installer des voix à partir d'archives locales. Après avoir obtenu le fichier de la voix, ouvrez le gestionnaire de voix, sous l'onglet Installé, cliquez sur le bouton intitulé `Installer à partir d'un fichier local`. Choisissez le fichier de la voix, attendez que la voix s'installe et redémarrez NVDA pour rafraîchir la liste des voix.

## Une note sur la qualité de la voix

Les voix actuellement disponibles sont formées à l'aide d'ensembles de données TTS disponibles gratuitement, qui sont généralement de mauvaise qualité (principalement des livres audio du domaine public ou des enregistrements de qualité de recherche).

De plus, ces ensembles de données ne sont pas exhaustifs, c'est pourquoi certaines voix peuvent présenter une prononciation incorrecte ou étrange. Les deux problèmes pourraient être résolus en utilisant de meilleurs ensembles de données pour la formation.

Heureusement, le développeur de `Piper` et certains développeurs de la communauté des aveugles et des malvoyants travaillent à la formation de meilleures voix.

# Licence

Copyright(c) 2024, Musharraf Omer. Ce logiciel est sous licence GNU GENERAL PUBLIC LICENSE Version 2 (GPL v2).
