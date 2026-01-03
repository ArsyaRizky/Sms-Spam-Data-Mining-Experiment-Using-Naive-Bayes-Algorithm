import { Controller, Get, Post, Body, Query, Req, UseGuards, BadRequestException } from '@nestjs/common';
import { StudentsService } from './students.service';
import { RolesGuard } from '../auth/guards/roles.guard';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { Roles } from '../auth/decorators/roles.decorator';
import { Public } from '../auth/decorators/public.decorator';
import { UserRole } from '../entities/user.entity';

@Controller('students')
@UseGuards(JwtAuthGuard, RolesGuard)
@Roles(UserRole.STUDENT)
export class StudentsController {
  constructor(private readonly studentsService: StudentsService) {}

  /**
   * GET /students/subjects
   * Get student's subjects with teacher info
   */
  @Get('subjects')
  async getSubjects(@Req() req) {
    return this.studentsService.getStudentSubjects(req.user.userId);
  }

  /**
   * GET /students/subjects/:subjectName/attendance
   * Get attendance history for a specific subject
   */
  @Get('subjects/attendance')
  async getSubjectAttendance(
    @Req() req,
    @Query('subject') subject: string,
  ) {
    return this.studentsService.getSubjectAttendanceHistory(
      req.user.userId,
      subject,
    );
  }

  /**
   * GET /students/schedule?day=Senin
   * Get student's schedule (all days or specific day)
   */
  @Get('schedule')
  async getSchedule(@Req() req, @Query('day') day?: string) {
    return this.studentsService.getStudentSchedule(req.user.userId, day);
  }

  /**
   * GET /students/attendance/history
   * Get all attendance history grouped by date
   */
  @Get('attendance/history')
  async getAttendanceHistory(@Req() req) {
    return this.studentsService.getAttendanceHistory(req.user.userId);
  }

  /**
   * GET /students/attendance/stats?period=1 Bulan
   * Get attendance statistics
   */
  @Get('attendance/stats')
  async getAttendanceStats(
    @Req() req,
    @Query('period') period?: string,
  ) {
    return this.studentsService.getAttendanceStats(req.user.userId, period);
  }

  /**
   * POST /students/qr/generate
   * Generate QR token for student attendance
   */
  @Post('qr/generate')
  async generateQRToken(@Req() req) {
    return this.studentsService.generateQRToken(req.user.userId);
  }

  /**
   * POST /students/qr/validate
   * Validate QR token and mark attendance (for Raspberry Pi scanner)
   * This endpoint is PUBLIC - no authentication required for scanner
   */
  @Public()
  @Post('qr/validate')
  async validateQRToken(
    @Body('token') token: string,
    @Body('session_id') sessionId?: number,
  ) {
    try {
      const result = await this.studentsService.validateQRToken(token, sessionId);
      return result;
    } catch (error) {
      // Return error in a format the scanner expects
      throw error;
    }
  }

  /**
   * GET /students/attendance/latest
   * Get latest attendance record for the student
   */
  @Get('attendance/latest')
  async getLatestAttendance(@Req() req) {
    return this.studentsService.getLatestAttendance(req.user.userId);
  }

  /**
   * GET /students/qr/check?token=abc123
   * Check if current QR token was scanned and get attendance
   */
  @Get('qr/check')
  async checkQRTokenStatus(@Req() req, @Query('token') token: string) {
    if (!token) {
      throw new BadRequestException('Token is required');
    }
    return this.studentsService.checkQRTokenAttendance(req.user.userId, token);
  }
}
