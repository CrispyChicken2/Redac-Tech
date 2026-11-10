<?xml version="1.0" encoding="UTF-8"?>
<!--
  Published (IETP-like) view of an S1000D data module. XSLT 1.0, no extension, no access to other files.
  Parameter show-deleted: '1' (default) shows the elements marked changeType="delete" struck
  through, '0' leaves them out. Unknown elements are rendered generically (name + content).
-->
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

  <xsl:output method="html" encoding="UTF-8" indent="no"/>

  <xsl:param name="show-deleted" select="'1'"/>

  <!-- ===== helpers ===== -->

  <!-- class attribute: base class + change bar / deleted class from the change marks -->
  <xsl:template name="cls">
    <xsl:param name="base"/>
    <xsl:attribute name="class">
      <xsl:value-of select="$base"/>
      <xsl:choose>
        <xsl:when test="@changeType = 'delete'"><xsl:text> rt-deleted</xsl:text></xsl:when>
        <xsl:when test="@changeMark = '1' and @changeType = 'add'"><xsl:text> rt-add</xsl:text></xsl:when>
        <xsl:when test="@changeMark = '1'"><xsl:text> rt-modify</xsl:text></xsl:when>
      </xsl:choose>
    </xsl:attribute>
  </xsl:template>

  <!-- class of a table row: the first change mark found on the row or below it -->
  <xsl:template name="row-cls">
    <xsl:param name="base"/>
    <xsl:attribute name="class">
      <xsl:value-of select="$base"/>
      <xsl:choose>
        <xsl:when test="descendant-or-self::*[@changeType = 'delete']"><xsl:text> rt-deleted</xsl:text></xsl:when>
        <xsl:when test="descendant-or-self::*[@changeMark = '1' and @changeType = 'add']"><xsl:text> rt-add</xsl:text></xsl:when>
        <xsl:when test="descendant-or-self::*[@changeMark = '1']"><xsl:text> rt-modify</xsl:text></xsl:when>
      </xsl:choose>
    </xsl:attribute>
  </xsl:template>

  <!-- ===== document ===== -->

  <xsl:template match="/">
    <div class="rt-doc">
      <xsl:apply-templates select="*[not(@changeType = 'delete' and $show-deleted = '0')]"/>
    </div>
  </xsl:template>

  <xsl:template match="dmodule">
    <xsl:variable name="title" select="identAndStatusSection/dmAddress/dmAddressItems/dmTitle"/>
    <xsl:if test="$title/techName or $title/infoName or $title/infoNameVariant">
      <h1 class="rt-title">
        <xsl:value-of select="$title/techName"/>
        <xsl:if test="$title/techName and $title/infoName"><xsl:text> - </xsl:text></xsl:if>
        <xsl:value-of select="$title/infoName"/>
        <xsl:if test="$title/infoNameVariant"><xsl:text> - </xsl:text><xsl:value-of select="$title/infoNameVariant"/></xsl:if>
      </h1>
    </xsl:if>
    <xsl:apply-templates select="identAndStatusSection/dmStatus/applic"/>
    <xsl:apply-templates select="content"/>
  </xsl:template>

  <xsl:template match="content">
    <xsl:apply-templates select="node()[not(@changeType = 'delete' and $show-deleted = '0')]"/>
  </xsl:template>

  <!-- applicability badge: the display text, else the assert values -->
  <xsl:template match="applic">
    <div class="rt-applic-line">
      <span class="rt-applic">
        <xsl:choose>
          <xsl:when test="displayText">
            <xsl:value-of select="normalize-space(displayText)"/>
          </xsl:when>
          <xsl:when test=".//assert">
            <xsl:for-each select=".//assert">
              <xsl:if test="position() &gt; 1"><xsl:text> / </xsl:text></xsl:if>
              <xsl:value-of select="@applicPropertyIdent"/>
              <xsl:text>=</xsl:text>
              <xsl:value-of select="@applicPropertyValues"/>
            </xsl:for-each>
          </xsl:when>
          <xsl:otherwise><xsl:text>Applicability not given</xsl:text></xsl:otherwise>
        </xsl:choose>
      </span>
    </div>
  </xsl:template>

  <!-- ===== procedures ===== -->

  <xsl:template match="procedure">
    <xsl:apply-templates select="node()[not(@changeType = 'delete' and $show-deleted = '0')]"/>
  </xsl:template>

  <xsl:template match="preliminaryRqmts">
    <div>
      <xsl:call-template name="cls"><xsl:with-param name="base" select="'rt-prelim'"/></xsl:call-template>
      <h2>Preliminary requirements</h2>
      <xsl:apply-templates select="*[not(@changeType = 'delete' and $show-deleted = '0')]"/>
    </div>
  </xsl:template>

  <xsl:template match="reqCondGroup | reqSafety">
    <div class="rt-req">
      <h3>
        <xsl:choose>
          <xsl:when test="self::reqSafety"><xsl:text>Safety</xsl:text></xsl:when>
          <xsl:otherwise><xsl:text>Conditions</xsl:text></xsl:otherwise>
        </xsl:choose>
      </h3>
      <xsl:choose>
        <xsl:when test="noConds or noSafety"><p class="rt-none">None</p></xsl:when>
        <xsl:otherwise><xsl:apply-templates select="node()[not(@changeType = 'delete' and $show-deleted = '0')]"/></xsl:otherwise>
      </xsl:choose>
    </div>
  </xsl:template>

  <!-- support equipment, supplies, spares: one table each -->
  <xsl:template match="reqSupportEquips">
    <div class="rt-req">
      <h3>Support equipment</h3>
      <xsl:choose>
        <xsl:when test=".//supportEquipDescr">
          <table class="rt-table">
            <tr><th>Name</th><th>Part number</th><th>Quantity</th></tr>
            <xsl:apply-templates select=".//supportEquipDescr[not(@changeType = 'delete' and $show-deleted = '0')]" mode="row"/>
          </table>
        </xsl:when>
        <xsl:otherwise><p class="rt-none">None</p></xsl:otherwise>
      </xsl:choose>
    </div>
  </xsl:template>

  <xsl:template match="reqSupplies">
    <div class="rt-req">
      <h3>Supplies</h3>
      <xsl:choose>
        <xsl:when test=".//supplyDescr">
          <table class="rt-table">
            <tr><th>Name</th><th>Part number</th><th>Quantity</th></tr>
            <xsl:apply-templates select=".//supplyDescr[not(@changeType = 'delete' and $show-deleted = '0')]" mode="row"/>
          </table>
        </xsl:when>
        <xsl:otherwise><p class="rt-none">None</p></xsl:otherwise>
      </xsl:choose>
    </div>
  </xsl:template>

  <xsl:template match="reqSpares">
    <div class="rt-req">
      <h3>Spares</h3>
      <xsl:choose>
        <xsl:when test=".//spareDescr">
          <table class="rt-table">
            <tr><th>Name</th><th>Part number</th><th>Quantity</th></tr>
            <xsl:apply-templates select=".//spareDescr[not(@changeType = 'delete' and $show-deleted = '0')]" mode="row"/>
          </table>
        </xsl:when>
        <xsl:otherwise><p class="rt-none">None</p></xsl:otherwise>
      </xsl:choose>
    </div>
  </xsl:template>

  <xsl:template match="supportEquipDescr | supplyDescr | spareDescr" mode="row">
    <tr>
      <xsl:call-template name="row-cls"><xsl:with-param name="base" select="'rt-row'"/></xsl:call-template>
      <td><xsl:value-of select="name"/></td>
      <td><xsl:value-of select="identNumber/partAndSerialNumber/partNumber"/></td>
      <td><xsl:value-of select="reqQuantity"/></td>
    </tr>
  </xsl:template>

  <xsl:template match="mainProcedure">
    <div class="rt-main">
      <h2>Procedure</h2>
      <xsl:apply-templates select="node()[not(@changeType = 'delete' and $show-deleted = '0')]"/>
    </div>
  </xsl:template>

  <xsl:template match="closeRqmts">
    <div class="rt-close">
      <h2>Close requirements</h2>
      <xsl:apply-templates select="node()[not(@changeType = 'delete' and $show-deleted = '0')]"/>
    </div>
  </xsl:template>

  <!-- numbered steps: 1, 1.1, 1.2 ... (deleted steps are not counted when hidden) -->
  <xsl:template match="proceduralStep">
    <div>
      <xsl:call-template name="cls"><xsl:with-param name="base" select="'rt-step'"/></xsl:call-template>
      <span class="rt-num">
        <xsl:choose>
          <xsl:when test="$show-deleted = '0'">
            <xsl:number level="multiple" count="proceduralStep[not(@changeType = 'delete')]" format="1.1"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:number level="multiple" count="proceduralStep" format="1.1"/>
          </xsl:otherwise>
        </xsl:choose>
      </span>
      <div class="rt-step-body">
        <xsl:apply-templates select="node()[not(@changeType = 'delete' and $show-deleted = '0')]"/>
      </div>
    </div>
  </xsl:template>

  <!-- ===== paragraphs, boxes, lists ===== -->

  <xsl:template match="para | simplePara">
    <p>
      <xsl:call-template name="cls"><xsl:with-param name="base" select="'rt-para'"/></xsl:call-template>
      <xsl:apply-templates select="node()[not(@changeType = 'delete' and $show-deleted = '0')]"/>
    </p>
  </xsl:template>

  <xsl:template match="warning">
    <div>
      <xsl:call-template name="cls"><xsl:with-param name="base" select="'rt-box rt-warning'"/></xsl:call-template>
      <div class="rt-box-title">WARNING</div>
      <xsl:apply-templates select="node()[not(@changeType = 'delete' and $show-deleted = '0')]"/>
    </div>
  </xsl:template>

  <xsl:template match="caution">
    <div>
      <xsl:call-template name="cls"><xsl:with-param name="base" select="'rt-box rt-caution'"/></xsl:call-template>
      <div class="rt-box-title">CAUTION</div>
      <xsl:apply-templates select="node()[not(@changeType = 'delete' and $show-deleted = '0')]"/>
    </div>
  </xsl:template>

  <xsl:template match="note">
    <div>
      <xsl:call-template name="cls"><xsl:with-param name="base" select="'rt-box rt-note'"/></xsl:call-template>
      <div class="rt-box-title">NOTE</div>
      <xsl:apply-templates select="node()[not(@changeType = 'delete' and $show-deleted = '0')]"/>
    </div>
  </xsl:template>

  <xsl:template match="warningAndCautionPara | notePara">
    <p class="rt-box-text"><xsl:apply-templates select="node()[not(@changeType = 'delete' and $show-deleted = '0')]"/></p>
  </xsl:template>

  <xsl:template match="randomList">
    <ul class="rt-list"><xsl:apply-templates select="listItem[not(@changeType = 'delete' and $show-deleted = '0')]"/></ul>
  </xsl:template>

  <xsl:template match="sequentialList">
    <ol class="rt-list"><xsl:apply-templates select="listItem[not(@changeType = 'delete' and $show-deleted = '0')]"/></ol>
  </xsl:template>

  <xsl:template match="listItem">
    <li>
      <xsl:call-template name="cls"><xsl:with-param name="base" select="'rt-li'"/></xsl:call-template>
      <xsl:apply-templates select="node()[not(@changeType = 'delete' and $show-deleted = '0')]"/>
    </li>
  </xsl:template>

  <xsl:template match="title">
    <div class="rt-subtitle"><xsl:apply-templates select="node()"/></div>
  </xsl:template>

  <xsl:template match="emphasis">
    <strong><xsl:apply-templates select="node()"/></strong>
  </xsl:template>

  <xsl:template match="internalRef">
    <span class="rt-ref"><xsl:text>[</xsl:text><xsl:value-of select="@internalRefId"/><xsl:text>]</xsl:text></span>
  </xsl:template>

  <xsl:template match="dmRef">
    <span class="rt-ref">
      <xsl:text>DM </xsl:text>
      <xsl:value-of select="dmRefIdent/dmCode/@modelIdentCode"/>
      <xsl:text>-</xsl:text>
      <xsl:value-of select="dmRefIdent/dmCode/@systemCode"/>
      <xsl:text>-</xsl:text>
      <xsl:value-of select="dmRefIdent/dmCode/@infoCode"/>
    </span>
  </xsl:template>

  <!-- ===== descriptions ===== -->

  <xsl:template match="description">
    <xsl:apply-templates select="node()[not(@changeType = 'delete' and $show-deleted = '0')]"/>
  </xsl:template>

  <xsl:template match="levelledPara">
    <div>
      <xsl:call-template name="cls"><xsl:with-param name="base" select="'rt-lp'"/></xsl:call-template>
      <xsl:apply-templates select="node()[not(@changeType = 'delete' and $show-deleted = '0')]"/>
    </div>
  </xsl:template>

  <!-- ===== figures: the image is never loaded, only the ICN is shown ===== -->

  <xsl:template match="figure">
    <div>
      <xsl:call-template name="cls"><xsl:with-param name="base" select="'rt-figure'"/></xsl:call-template>
      <xsl:apply-templates select="node()[not(@changeType = 'delete' and $show-deleted = '0')]"/>
    </div>
  </xsl:template>

  <xsl:template match="graphic">
    <div>
      <xsl:call-template name="cls"><xsl:with-param name="base" select="'rt-icn'"/></xsl:call-template>
      <span class="rt-icn-id"><xsl:text>ICN </xsl:text><xsl:value-of select="@infoEntityIdent"/></span>
    </div>
  </xsl:template>

  <!-- ===== illustrated parts data ===== -->

  <xsl:template match="illustratedPartsCatalog">
    <div class="rt-ipd">
      <h2>Illustrated parts data</h2>
      <xsl:apply-templates select="figure[not(@changeType = 'delete' and $show-deleted = '0')]"/>
      <table class="rt-table">
        <tr><th>Item</th><th>Part number</th><th>Quantity</th><th>Description</th></tr>
        <xsl:apply-templates select="catalogSeqNumber[not(@changeType = 'delete' and $show-deleted = '0')]" mode="row"/>
      </table>
    </div>
  </xsl:template>

  <xsl:template match="catalogSeqNumber" mode="row">
    <tr>
      <xsl:call-template name="row-cls"><xsl:with-param name="base" select="'rt-row'"/></xsl:call-template>
      <td>
        <xsl:choose>
          <xsl:when test="@item"><xsl:value-of select="@item"/></xsl:when>
          <xsl:otherwise><xsl:value-of select="itemSeqNumber/@itemSeqNumberValue"/></xsl:otherwise>
        </xsl:choose>
      </td>
      <td><xsl:value-of select="itemSeqNumber/partRef/@partNumberValue"/></td>
      <td><xsl:value-of select="itemSeqNumber/quantityPerNextHigherAssy"/></td>
      <td><xsl:value-of select="itemSeqNumber/partSegment/itemIdentData/descrForPart"/></td>
    </tr>
  </xsl:template>

  <!-- ===== common information repositories ===== -->

  <xsl:template match="commonRepository">
    <div class="rt-comrep">
      <xsl:apply-templates select="*[not(@changeType = 'delete' and $show-deleted = '0')]"/>
    </div>
  </xsl:template>

  <xsl:template match="partRepository">
    <h2>Parts</h2>
    <table class="rt-table">
      <tr><th>Part number</th><th>Manufacturer</th><th>Description</th></tr>
      <xsl:apply-templates select="partSpec[not(@changeType = 'delete' and $show-deleted = '0')]" mode="row"/>
    </table>
  </xsl:template>

  <xsl:template match="partSpec" mode="row">
    <tr>
      <xsl:call-template name="row-cls"><xsl:with-param name="base" select="'rt-row'"/></xsl:call-template>
      <td><xsl:value-of select="partIdent/@partNumberValue"/></td>
      <td><xsl:value-of select="partIdent/@manufacturerCodeValue"/></td>
      <td><xsl:value-of select="itemIdentData/descrForPart"/></td>
    </tr>
  </xsl:template>

  <xsl:template match="toolRepository">
    <h2>Tools</h2>
    <table class="rt-table">
      <tr><th>Tool number</th><th>Manufacturer</th><th>Description</th></tr>
      <xsl:apply-templates select="toolSpec[not(@changeType = 'delete' and $show-deleted = '0')]" mode="row"/>
    </table>
  </xsl:template>

  <xsl:template match="toolSpec" mode="row">
    <tr>
      <xsl:call-template name="row-cls"><xsl:with-param name="base" select="'rt-row'"/></xsl:call-template>
      <td><xsl:value-of select="toolIdent/@toolNumber"/></td>
      <td><xsl:value-of select="toolIdent/@manufacturerCodeValue"/></td>
      <td><xsl:value-of select="itemIdentData/descrForPart"/></td>
    </tr>
  </xsl:template>

  <xsl:template match="supplyRepository">
    <h2>Supplies</h2>
    <table class="rt-table">
      <tr><th>Supply number</th><th>Manufacturer</th><th>Description</th></tr>
      <xsl:apply-templates select="supplySpec[not(@changeType = 'delete' and $show-deleted = '0')]" mode="row"/>
    </table>
  </xsl:template>

  <xsl:template match="supplySpec" mode="row">
    <tr>
      <xsl:call-template name="row-cls"><xsl:with-param name="base" select="'rt-row'"/></xsl:call-template>
      <td><xsl:value-of select="supplyIdent/@supplyNumber"/></td>
      <td><xsl:value-of select="supplyIdent/@manufacturerCodeValue"/></td>
      <td><xsl:value-of select="itemIdentData/descrForPart"/></td>
    </tr>
  </xsl:template>

  <!-- ===== anything else: its name and its content, never an error ===== -->

  <xsl:template match="*">
    <div>
      <xsl:call-template name="cls"><xsl:with-param name="base" select="'rt-unknown'"/></xsl:call-template>
      <span class="rt-unknown-name"><xsl:value-of select="name()"/></span>
      <xsl:text> </xsl:text>
      <xsl:apply-templates select="node()[not(@changeType = 'delete' and $show-deleted = '0')]"/>
    </div>
  </xsl:template>

</xsl:stylesheet>
