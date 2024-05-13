from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (QgsProcessingParameterEnum, QgsProcessingParameterRasterLayer,
                       QgsProcessingParameterVectorLayer, QgsProcessingAlgorithm, QgsPoint,
                       QgsProcessingOutputVectorLayer, QgsProcessingFeedback, QgsProcessingContext,
                       QgsVectorLayer, QgsFields, QgsFeature, QgsField, QgsProject, QgsVectorFileWriter, QgsGeometry,
                       QgsProcessingParameterFeatureSink,QgsProcessingException,QgsLineSymbol,QgsSingleSymbolRenderer,QgsFeatureRequest,
                       QgsSymbol, QgsRuleBasedRenderer, QgsFeatureRenderer,QgsWkbTypes,QgsRendererCategory,QgsCategorizedSymbolRenderer,QgsSpatialIndex)
import uuid
import processing



class CriarCamadasCurvasNivelMod(QgsProcessingAlgorithm):
    ESCALAS = ['1:25.000', '1:50.000', '1:100.000', '1:250.000']
    ESCALA_PARAMETER = 'ESCALA'
    MDT_PARAMETER = 'MDT'
    CURVAS_NIVEL_PARAMETER = 'CURVAS_NIVEL'
    PISTA_P_PARAMETER = 'PISTA_P'
    PISTA_L_PARAMETER = 'PISTA_L'
    PISTA_A_PARAMETER = 'PISTA_A'
    AREA_PONTO_COTADO = 'AREA_PONTO_COTADO'
    OUTPUT_CURVAS_NIVEL = 'OUTPUT_CURVAS_NIVEL'
    OUTPUT_PISTA_P = 'OUTPUT_PISTA_P'
    OUTPUT_PISTA_L = 'OUTPUT_PISTA_L'
    OUTPUT_PISTA_A = 'OUTPUT_PISTA_A'
    OUTPUT_PONTOS_ALTOS = 'OUTPUT_PONTOS_ALTOS'
    def name(self):
        return 'criar_camadas_curvas_nivel_mod'

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterEnum(
                self.ESCALA_PARAMETER,
                self.tr('Escala'),
                options=self.ESCALAS
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.MDT_PARAMETER,
                self.tr('Modelo Digital de Terreno')
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.CURVAS_NIVEL_PARAMETER,
                self.tr('Camada de Curvas de Nível')
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.PISTA_P_PARAMETER,
                self.tr('Pistas de Pouso (Pontos)')
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.AREA_PONTO_COTADO,
                self.tr('Area de Ponto Cotado')
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.PISTA_L_PARAMETER,
                self.tr('Pistas de Pouso (Linhas)')
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.PISTA_A_PARAMETER,
                self.tr('Pistas de Pouso (Polígonos)')
            )
        )
        self.addOutput(
            QgsProcessingOutputVectorLayer(
                self.OUTPUT_CURVAS_NIVEL,
                self.tr('Camada de Curvas de Nível Modificada')
            )
        )
        self.addOutput(
            QgsProcessingOutputVectorLayer(
                self.OUTPUT_PONTOS_ALTOS,
                self.tr('Pontos altos identificados')
            )
        )
        self.addOutput(
            QgsProcessingOutputVectorLayer(
                self.OUTPUT_PISTA_P,
                self.tr('Pistas de Pouso (Pontos) Modificada')
            )
        )
        self.addOutput(
            QgsProcessingOutputVectorLayer(
                self.OUTPUT_PISTA_L,
                self.tr('Pistas de Pouso (Linhas) Modificada')
            )
        )
        self.addOutput(
            QgsProcessingOutputVectorLayer(
                self.OUTPUT_PISTA_A,
                self.tr('Pistas de Pouso (Polígonos) Modificada')
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        # OBJETIVO 1
        #Definições iniciais e seleção dos parametros
        escala = self.ESCALAS[parameters[self.ESCALA_PARAMETER]]
        equidistancia = self.obter_equidistancia(escala)
        mdt_layer = self.parameterAsRasterLayer(parameters, self.MDT_PARAMETER, context)
        curvas_nivel_layer = self.parameterAsVectorLayer(parameters, self.CURVAS_NIVEL_PARAMETER, context)
        fields = curvas_nivel_layer.fields()

        #Criação da camada de memória
        feedback.pushInfo('Gerando a nova camada de Cuvas de Nível')
        mem_layer = QgsVectorLayer("LineString?crs=EPSG:4674", "result", "memory")
        provider = mem_layer.dataProvider()
        provider.addAttributes(fields)
        provider.addAttributes([QgsField('tipo', QVariant.String)])
        mem_layer.updateFields()

      #Cada curva de nível é examinada para determinar se é uma curva mestra ou normal, com base em sua cota e na equidistância.
        for feature in curvas_nivel_layer.getFeatures():
            cota = feature['cota']
            if cota % equidistancia == 0:
                tipo = 'mestra' if cota % (5 * equidistancia) == 0 else 'normal'
                new_feature = QgsFeature()
                new_feature.setGeometry(feature.geometry())
                new_attributes = {field.name(): feature[field.name()] for field in fields}
                new_attributes['tipo'] = tipo
                new_feature.setAttributes(list(new_attributes.values()))
                provider.addFeature(new_feature)

        if mem_layer.featureCount() == 0:
            feedback.pushWarning("A nova camada de curvas de nível está vazia.")
        else:
            feedback.pushInfo(f"A nova camada de curvas de nível resultante contém {mem_layer.featureCount()} feições e foi gerada com sucesso.")
      #Salvando a camada memoria
        save_options = QgsVectorFileWriter.SaveVectorOptions()
        temp_file_name = f'output_memory_{uuid.uuid4()}'
        writer_error, error_message, new_filename, output_format = QgsVectorFileWriter.writeAsVectorFormatV3(
            mem_layer,
            temp_file_name,
            context.transformContext(),
            save_options
        )

        if writer_error != QgsVectorFileWriter.WriterError.NoError:
            raise QgsProcessingException(f"Erro ao salvar a camada de curvas de nível modificada: {error_message}")

        layer = QgsVectorLayer(new_filename, "Camada de Curvas de Nível Modificada", "ogr")
        if not layer.isValid():
            raise QgsProcessingException(f"Erro ao carregar a nova camada de curvas de nível: {layer.error()}")

        field_name = "tipo"
        master_value = "mestra"
        normal_value = "normal"
        default_symbol = QgsSymbol.defaultSymbol(QgsWkbTypes.LineGeometry)
        master_line_symbol = QgsLineSymbol.createSimple({'width': '1.2', 'color': 'red', 'style': 'solid'})
        normal_line_symbol = QgsLineSymbol.createSimple({'width': '1', 'color': 'red', 'style': 'solid'})
        categories = []
        categories.append(QgsRendererCategory(master_value, master_line_symbol, 'Curvas Mestras'))
        categories.append(QgsRendererCategory(normal_value, default_symbol, 'Curvas Normais'))
        renderer = QgsCategorizedSymbolRenderer(field_name, categories)
        layer.setRenderer(renderer)
        QgsProject.instance().addMapLayer(layer)

        # OBJETIVO 2
      # # Etapa 1: Criar uma camada de pontos em grade com base no raster do MDT

      #   # Executa o algoritmo "Pixels de raster para pontos"
      #   feedback.pushInfo('Convertendo raster para pontos...')
      #   #result = processing.run("native:pixelstopoints", {'INPUT_RASTER':mdt_layer,'RASTER_BAND':1,'FIELD_NAME':'cota','OUTPUT':'TEMPORARY_OUTPUT'})
      #   resultado_processing = processing.run("native:pixelstopoints", {'INPUT_RASTER':mdt_layer,'RASTER_BAND':1,'FIELD_NAME':'cota','OUTPUT':'TEMPORARY_OUTPUT'})
      #   pontos_layer = resultado_processing['OUTPUT']
      #   feedback.pushInfo('MDT transformado para grade de pontos.')

      # Etapa 2: Calcular o atributo 'altitude' para cada tipo de camada de pista de pouso

      # # Calcula a altitude para a camada de pontos de pista de pouso
      #   feedback.pushInfo('Calculando a nova camada de pista de pouso (pontos) com as altitudes.')

      #   nova_camada_pontos = self.calcular_altitude_pontos(pista_pontos_layer, pontos_layer, context, feedback)

      #   feedback.pushInfo('Nova camada de pista de pouso (pontos) calculada com sucesso.')


      #   # Calcula a altitude para a camada de linhas de pista de pouso
      #   feedback.pushInfo('Calculando a nova camada de pista de pouso (linhas) com as altitudes.')

      #   nova_camada_linhas = self.calcular_altitude_linhas(pista_linhas_layer, pontos_layer, context, feedback)

      #   feedback.pushInfo('Nova camada de pista de pouso (linhas) calculada com sucesso.')


      #   # Calcula a altitude para a camada de polígonos de pista de pouso
      #   feedback.pushInfo('Calculando a nova camada de pista de pouso (poligonos) com as altitudes.')

      #   nova_camada_poligonos = self.calcular_altitude_poligonos(pista_poligonos_layer, pontos_layer, context, feedback)

      #   feedback.pushInfo('Nova camada de pista de pouso (poligonos) calculada com sucesso.')        


      #   return {self.OUTPUT_CURVAS_NIVEL: layer, self.OUTPUT_PISTA_P: nova_camada_pontos, self.OUTPUT_PISTA_L: nova_camada_linhas, self.OUTPUT_PISTA_A: nova_camada_poligonos}

      
        feedback.pushInfo('Identificando o ponto mais alto dentro de demarcações de curva de nível')
        pontos_layer = self.parameterAsVectorLayer(parameters, 'CURVAS_NIVEL', context)
        index = QgsSpatialIndex(pontos_layer.getFeatures())
        pontos_curvas_nivel = {}

        area_ponto_cotado_layer = self.parameterAsVectorLayer(parameters, 'AREA_PONTO_COTADO', context)
        area_ponto_cotado_geometry = next(area_ponto_cotado_layer.getFeatures()).geometry()

        for curva_feature in layer.getFeatures():
            curva_geom = curva_feature.geometry()
            ponto_mais_alto = None
            altura_maxima = float('-inf')

            #Analisando se a geometria da curva e do ponto são polígonos
            #Verifica se a geometria da curva é um polígono e se os pontos são do tipo ponto.
            #Checa se o ponto está dentro da curva e se está contido na área designada para cotação.
            if curva_geom.wkbType() == QgsWkbTypes.Polygon and ponto_geometry.wkbType() == QgsWkbTypes.Point:
                for ponto_feature in pontos_layer.getFeatures():
                    ponto_geom = ponto_feature.geometry()
                    if ponto_geom.within(curva_geom) and area_ponto_cotado_geometry.contains(ponto_geom):
                        altitude = ponto_feature['cota']
                        if altitude > altura_maxima:
                            altura_maxima = altitude
                            ponto_mais_alto = ponto_geom

            if ponto_mais_alto:
                #Geometria é uma QgsPointXY?
                if ponto_mais_alto.type() == QgsWkbTypes.Point:
                    #Convertendo QgsPointXY para QgsPoint
                    ponto_mais_alto = QgsPoint(ponto_mais_alto.x(), ponto_mais_alto.y())
                elif ponto_mais_alto.type() == QgsWkbTypes.MultiLineString:
                    #Se for MultiLineString, extraímos o primeiro ponto
                    ponto_mais_alto = ponto_mais_alto.asMultiPolyline()[0][0]
                else:
                    #Se não for nem QgsPointXY nem MultiLineString, há um erro na geometria
                    raise QgsProcessingException("Geometria inválida para o ponto mais alto")
                
                pontos_curvas_nivel[curva_feature.id()] = ponto_mais_alto



        feedback.pushInfo('Pontos mais altos identificados.')

        #Criando uma nova camada para os pontos mais altos
        nova_camada_pontos_altos = QgsVectorLayer("Point?crs=EPSG:4326", "Pontos Cotados Mais Altos", "memory")
        provider_altos = nova_camada_pontos_altos.dataProvider()
        provider_altos.addAttributes([QgsField('altitude', QVariant.Double, 'double', 10, 1)])
        nova_camada_pontos_altos.updateFields()

        for curva_id, ponto_mais_alto in pontos_curvas_nivel.items():
            nova_feature = QgsFeature()
            nova_feature.setGeometry(QgsGeometry.fromPointXY(ponto_mais_alto.asPoint()))
            nova_feature.setAttributes([pontos_layer.getFeature(curva_id)['cota']])
            provider_altos.addFeature(nova_feature)

        save_options_altos = QgsVectorFileWriter.SaveVectorOptions()
        temp_file_name_altos = f'output_memory_{uuid.uuid4()}'
        writer_error_altos, error_message_altos, new_filename_altos, output_format_altos = QgsVectorFileWriter.writeAsVectorFormatV3(
            nova_camada_pontos_altos,
            temp_file_name_altos,
            context.transformContext(),
            save_options_altos
        )

        if writer_error_altos != QgsVectorFileWriter.WriterError.NoError:
            raise QgsProcessingException(f"Erro ao salvar a camada de pontos mais altos cotados: {error_message_altos}")

        layer_pontos_altos = QgsVectorLayer(new_filename_altos, "Pontos Cotados Mais Altos", "ogr")
        if not layer_pontos_altos.isValid():
            raise QgsProcessingException(f"Erro ao carregar a camada de pontos mais altos cotados: {layer_pontos_altos.error()}")

        QgsProject.instance().addMapLayer(layer_pontos_altos)

        pista_pontos_layer = self.parameterAsVectorLayer(parameters, self.PISTA_P_PARAMETER, context)
        pista_linhas_layer = self.parameterAsVectorLayer(parameters, self.PISTA_L_PARAMETER, context)
        pista_poligonos_layer = self.parameterAsVectorLayer(parameters, self.PISTA_A_PARAMETER, context)

        # Calcula a altitude para a camada de pontos de pista de pouso
        feedback.pushInfo('Calculando a nova camada de pista de pouso (pontos) com as altitudes.')

        nova_camada_pontos = self.calcular_altitude_pontos(pista_pontos_layer, pontos_layer, context, feedback)

        feedback.pushInfo('Nova camada de pista de pouso (pontos) calculada com sucesso.')


        # Calcula a altitude para a camada de linhas de pista de pouso
        feedback.pushInfo('Calculando a nova camada de pista de pouso (linhas) com as altitudes.')

        nova_camada_linhas = self.calcular_altitude_linhas(pista_linhas_layer, pontos_layer, context, feedback)

        feedback.pushInfo('Nova camada de pista de pouso (linhas) calculada com sucesso.')


        # Calcula a altitude para a camada de polígonos de pista de pouso
        feedback.pushInfo('Calculando a nova camada de pista de pouso (poligonos) com as altitudes.')

        nova_camada_poligonos = self.calcular_altitude_poligonos(pista_poligonos_layer, pontos_layer, context, feedback)

        feedback.pushInfo('Nova camada de pista de pouso (poligonos) calculada com sucesso.')        

        return {
            self.OUTPUT_CURVAS_NIVEL: layer,
            self.OUTPUT_PISTA_P: nova_camada_pontos, 
            self.OUTPUT_PISTA_L: nova_camada_linhas, 
            self.OUTPUT_PISTA_A: nova_camada_poligonos,
            self.OUTPUT_PONTOS_ALTOS: layer_pontos_altos
        }



       #return {self.OUTPUT_CURVAS_NIVEL: layer, self.OUTPUT_PISTA_P: nova_camada_pontos, self.OUTPUT_PISTA_L: nova_camada_linhas, self.OUTPUT_PISTA_A: nova_camada_poligonos}

    def calcular_altitude_pontos(self, pista_pontos_layer, pontos_layer,context,feedback):
        nova_camada_pontos = QgsVectorLayer("Point?crs=EPSG:4326", "Pistas de Pouso (Pontos) Modificada", "memory")
        provider = nova_camada_pontos.dataProvider()
        fields = pista_pontos_layer.fields()
        fields.append(QgsField('altitude', QVariant.Double, 'double', 10, 1))
        provider.addAttributes(fields)
        nova_camada_pontos.updateFields()

        # Construir um índice espacial para os pontos gerados pelo MDT
        index = QgsSpatialIndex(pontos_layer.getFeatures())

        for feature in pista_pontos_layer.getFeatures():
            ponto_pista = feature.geometry().asPoint()
            nearest_ids = index.nearestNeighbor(ponto_pista, 1)
            if nearest_ids:
                nearest_feature = pontos_layer.getFeature(nearest_ids[0])
                altitude = nearest_feature['cota']
                # Arredonda a altitude para 1 casa decimal
                altitude_formatada = round(altitude, 1)
                feature['altitude'] = altitude_formatada
                provider.addFeature(feature)
        
        # Verificar se a camada de memória está vazia
        if nova_camada_pontos.featureCount() == 0:
            feedback.pushWarning("A camada pista pontos está vazia.")
        else:
            feedback.pushInfo(f"A camada pista pontos contém {nova_camada_pontos.featureCount()} feições.")

        # Salvar a camada de memória
        save_options = QgsVectorFileWriter.SaveVectorOptions()
        temp_file_name = f'output_memory_{uuid.uuid4()}'
        writer_error, error_message, new_filename, output_format = QgsVectorFileWriter.writeAsVectorFormatV3(
            nova_camada_pontos,
            temp_file_name,
            context.transformContext(),
            save_options
        )

        # Verificar se houve erro ao salvar
        if writer_error != QgsVectorFileWriter.WriterError.NoError:
            raise QgsProcessingException(f"Erro ao salvar a camada de pista pontos modificada: {error_message}")

        # Carregar a camada resultante
        layer_nova_camada_pontos = QgsVectorLayer(new_filename, "Camada de Pista Pontos Modificada", "ogr")
        if not layer_nova_camada_pontos.isValid():
            raise QgsProcessingException(f"Erro ao carregar a camada resultante: {layer_nova_camada_pontos.error()}")

        QgsProject.instance().addMapLayer(layer_nova_camada_pontos)
        return nova_camada_pontos

    def calcular_altitude_linhas(self, pista_linhas_layer, pontos_layer,context,feedback):
        # Implementar o cálculo da altitude para a camada de linhas de pista de pouso
        nova_camada_linhas = QgsVectorLayer("LineString?crs=EPSG:4326", "Pistas de Pouso (Linhas) Modificada", "memory")
        provider = nova_camada_linhas.dataProvider()
        fields = pista_linhas_layer.fields()
        fields.append(QgsField('altitude', QVariant.Double, 'double', 10, 1))
        provider.addAttributes(fields)
        nova_camada_linhas.updateFields()

        for feature in pista_linhas_layer.getFeatures():
            linha_geom = feature.geometry()
            buffer_geom = linha_geom.buffer(1, 5)  # Buffer de 1 metro
            altitude_total = 0
            count = 0
            for ponto_feature in pontos_layer.getFeatures():
                ponto_geom = ponto_feature.geometry()
                if buffer_geom.contains(ponto_geom):
                    altitude_total += ponto_feature['cota']
                    count += 1
            if count > 0:
                altitude_media = altitude_total / count
                altitude_formatada = round(altitude_media, 1)
                feature['altitude'] = altitude_formatada
                provider.addFeature(feature)
        #Se houver pontos dentro do buffer, a média das altitudes é calculada
        # Verificar se a camada de memória está vazia
        if nova_camada_linhas.featureCount() == 0:
            feedback.pushWarning("A camada pista linhas está vazia.")
        else:
            feedback.pushInfo(f"A camada pista linhas contém {nova_camada_linhas.featureCount()} feições.")

        # Salvar a camada de memória
        save_options = QgsVectorFileWriter.SaveVectorOptions()
        temp_file_name = f'output_memory_{uuid.uuid4()}'
        writer_error, error_message, new_filename, output_format = QgsVectorFileWriter.writeAsVectorFormatV3(
            nova_camada_linhas,
            temp_file_name,
            context.transformContext(),
            save_options
        )

        # Verificar se houve erro ao salvar
        if writer_error != QgsVectorFileWriter.WriterError.NoError:
            raise QgsProcessingException(f"Erro ao salvar a camada de pista linhas modificada: {error_message}")

        # Carregar a camada resultante
        layer_nova_camada_linhas = QgsVectorLayer(new_filename, "Camada de Pista Linhas Modificada", "ogr")
        if not layer_nova_camada_linhas.isValid():
            raise QgsProcessingException(f"Erro ao carregar a camada resultante: {layer_nova_camada_linhas.error()}")
        
        QgsProject.instance().addMapLayer(layer_nova_camada_linhas)

        return nova_camada_linhas

    def calcular_altitude_poligonos(self, pista_poligonos_layer, pontos_layer,context,feedback):
        # Implementar o cálculo da altitude para a camada de polígonos de pista de pouso
        nova_camada_poligonos = QgsVectorLayer("Polygon?crs=EPSG:4326", "Pistas de Pouso (Polígonos) Modificada", "memory")
        provider = nova_camada_poligonos.dataProvider()
        fields = pista_poligonos_layer.fields()
        fields.append(QgsField('altitude', QVariant.Double, 'double', 10, 1))
        provider.addAttributes(fields)
        nova_camada_poligonos.updateFields()

        for feature in pista_poligonos_layer.getFeatures():
            poligono_geom = feature.geometry()
            altitude_total = 0
            count = 0
            for ponto_feature in pontos_layer.getFeatures():
                ponto_geom = ponto_feature.geometry()
                if poligono_geom.contains(ponto_geom):
                    altitude_total += ponto_feature['cota']
                    count += 1
            if count > 0:
                altitude_media = altitude_total / count
                altitude_formatada = round(altitude_media, 1)
                feature['altitude'] = altitude_formatada
                provider.addFeature(feature)
        
        # Verificar se a camada de memória está vazia
        if nova_camada_poligonos.featureCount() == 0:
            feedback.pushWarning("A camada pista poligonos está vazia.")
        else:
            feedback.pushInfo(f"A camada pista poligonos contém {nova_camada_poligonos.featureCount()} feições.")

        # Salvar a camada de memória
        save_options = QgsVectorFileWriter.SaveVectorOptions()
        temp_file_name = f'output_memory_{uuid.uuid4()}'
        writer_error, error_message, new_filename, output_format = QgsVectorFileWriter.writeAsVectorFormatV3(
            nova_camada_poligonos,
            temp_file_name,
            context.transformContext(),
            save_options
        )

        # Verificar se houve erro ao salvar
        if writer_error != QgsVectorFileWriter.WriterError.NoError:
            raise QgsProcessingException(f"Erro ao salvar a camada de pista poligonos modificada: {error_message}")

        # Carregar a camada resultante
        layer_nova_camada_poligonos = QgsVectorLayer(new_filename, "Camada de Pista Poligonos Modificada", "ogr")
        if not layer_nova_camada_poligonos.isValid():
            raise QgsProcessingException(f"Erro ao carregar a camada resultante: {layer_nova_camada_poligonos.error()}")

        QgsProject.instance().addMapLayer(layer_nova_camada_poligonos)

        return nova_camada_poligonos


    def obter_equidistancia(self, escala):
        if escala == '1:25.000':
            return 10
        elif escala == '1:50.000':
            return 20
        elif escala == '1:100.000':
            return 50
        elif escala == '1:250.000':
            return 100

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return CriarCamadasCurvasNivelMod()

    def name(self):
        return 'criar_camadas_curvas_nivel_mod'

    def displayName(self):
        return self.tr('Criar Camadas de Curvas de Nível Modificadas')

    def group(self):
        return self.tr('Exemplo Scripts')

    def groupId(self):
        return 'examplescripts'

    def shortHelpString(self):
        return self.tr('Este algoritmo cria camadas de curvas de nível modificadas com base na escala selecionada.')
