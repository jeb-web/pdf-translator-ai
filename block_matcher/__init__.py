#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Block Matcher - Interface de matching manuel PyMuPDF/MinerU

Package pour la correction manuelle des correspondances entre
les blocs détectés par MinerU et les spans extraits par PyMuPDF.
"""

__version__ = "1.0.0"
__author__ = "Your Name"

from .main import main

__all__ = ['main']
